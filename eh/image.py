"""eh.image — fabrique le support bootable, spécifique à l'OS.

Linux : image disque GPT+FAT32 (rootless, mtools+sgdisk) → clé USB ou VM QEMU.
Windows : écriture directe sur une clé USB (diskpart), avec confirmation.
Les deux préparent le même contenu ESP : EFI/ + com.apple.recovery.boot/.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from . import common as c


def _dir_size(p: Path) -> int:
    if not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _esp_mb() -> int:
    total = _dir_size(c.EFI) + _dir_size(c.RECOVERY)
    return max(512, total // (1 << 20) + 350)


def _recovery_files() -> list[Path]:
    if not c.RECOVERY.exists():
        return []
    return [f for f in c.RECOVERY.iterdir() if f.is_file()]


# --------------------------------------------------------------------------- Linux
def _need(*cmds: str) -> None:
    missing = [x for x in cmds if not shutil.which(x)]
    if missing:
        c.die(f"commande(s) manquante(s) : {', '.join(missing)} "
              f"(installe mtools + gptfdisk)")


def _make_gpt(img: Path, gap: int, esp_sectors: int) -> None:
    """Crée une table GPT avec une partition ESP (EF00). sgdisk sinon sfdisk."""
    if shutil.which("sgdisk"):
        subprocess.run(["sgdisk", "-o", str(img)], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["sgdisk", "-a", "1", "-n",
                        f"1:{gap}:{gap + esp_sectors - 1}", "-t", "1:EF00",
                        "-c", "1:EFI", str(img)], check=True, stdout=subprocess.DEVNULL)
    else:  # fallback util-linux (presque toujours présent)
        script = f"label: gpt\nstart={gap}, size={esp_sectors}, type=uefi, name=EFI\n"
        subprocess.run(["sfdisk", str(img)], input=script, text=True,
                       check=True, stdout=subprocess.DEVNULL)


def _build_linux(ver_key: str) -> Path:
    c.title("Fabrication de l'image bootable (Linux)")
    _need("mformat", "mcopy", "mmd", "truncate", "dd")
    if not (shutil.which("sgdisk") or shutil.which("sfdisk")):
        c.die("sgdisk (gptfdisk) ou sfdisk (util-linux) requis")
    mb = _esp_mb()
    esp_sectors = mb * 2048
    esp = c.OUT / "esp.img"
    img = c.OUT / f"macOS-{ver_key}.img"
    for p in (esp, img):
        p.unlink(missing_ok=True)
    c.log(f"ESP : {mb} Mo")

    subprocess.run(["mformat", "-C", "-i", str(esp), "-T", str(esp_sectors),
                    "-F", "-v", "EFIBOOT", "::"], check=True)
    subprocess.run(["mmd", "-i", str(esp), "::/EFI"], check=True)
    subprocess.run(["mcopy", "-i", str(esp), "-s", str(c.EFI / "BOOT"), "::/EFI/"], check=True)
    subprocess.run(["mcopy", "-i", str(esp), "-s", str(c.EFI / "OC"), "::/EFI/"], check=True)
    subprocess.run(["mmd", "-i", str(esp), "::/com.apple.recovery.boot"], check=True)
    for f in _recovery_files():
        subprocess.run(["mcopy", "-i", str(esp), str(f),
                        "::/com.apple.recovery.boot/"], check=True)

    gap = 2048
    total = gap + esp_sectors + 2048
    subprocess.run(["truncate", "-s", str(total * 512), str(img)], check=True)
    _make_gpt(img, gap, esp_sectors)
    subprocess.run(["dd", f"if={esp}", f"of={img}", "bs=512", f"seek={gap}",
                    "conv=notrunc", "status=none"], check=True)
    esp.unlink(missing_ok=True)
    c.ok(f"Image prête : {img}")
    _write_qemu_helper(img)
    return img


def _write_qemu_helper(img: Path) -> None:
    ovmf = "/usr/share/edk2/x64/OVMF_CODE.4m.fd"
    if not Path(ovmf).exists():
        ovmf = "/usr/share/OVMF/OVMF_CODE.fd"
    script = c.OUT / "run-qemu.sh"
    script.write_text(f"""#!/usr/bin/env bash
# Test rapide de l'image en VM (qemu + edk2-ovmf requis).
IMG="${{1:-{img}}}"
OVMF="${{OVMF:-{ovmf}}}"
qemu-system-x86_64 \\
  -machine q35 -cpu Penryn,vendor=GenuineIntel,+ssse3,+sse4.1,+sse4.2,+popcnt \\
  -smp 4 -m 4096 -accel kvm \\
  -drive if=pflash,format=raw,readonly=on,file="$OVMF" \\
  -device qemu-xhci -device usb-kbd -device usb-tablet \\
  -drive id=install,if=none,format=raw,file="$IMG" \\
  -device ide-hd,bus=ide.0,drive=install \\
  -netdev user,id=net0 -device vmxnet3,netdev=net0 -vga vmware
""")
    script.chmod(0o755)
    c.ok(f"Helper VM : {script}")


# --------------------------------------------------------------------------- Windows
def _stage_windows() -> Path:
    stage = c.OUT / "ESP"
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "EFI").mkdir(parents=True)
    shutil.copytree(c.EFI / "BOOT", stage / "EFI" / "BOOT")
    shutil.copytree(c.EFI / "OC", stage / "EFI" / "OC")
    rec = stage / "com.apple.recovery.boot"
    rec.mkdir()
    for f in _recovery_files():
        shutil.copy2(f, rec / f.name)
    return stage


def _ps(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                           "-Command", script], capture_output=True, text=True)


def _build_windows(ver_key: str) -> Path | None:
    c.title("Écriture sur clé USB (Windows)")
    stage = _stage_windows()
    c.ok(f"Contenu ESP préparé : {stage}")

    # Liste des disques USB amovibles
    out = _ps("Get-Disk | Where-Object BusType -eq 'USB' | "
              "ForEach-Object { \"$($_.Number)|$($_.FriendlyName)|"
              "$([math]::Round($_.Size/1GB,1))GB\" }").stdout.strip()
    if not out:
        c.warn("Aucune clé USB détectée. Contenu prêt dans le dossier ci-dessus : "
               "formate une clé en FAT32 (GPT) et copie EFI/ + com.apple.recovery.boot/ à la racine.")
        return None

    print("Clés USB détectées :")
    for line in out.splitlines():
        num, name, size = line.split("|")
        print(f"  disque {num} — {name} ({size})")
    try:
        num = input("Numéro du disque à EFFACER et préparer : ").strip()
    except EOFError:
        c.die("Sélection requise (mode interactif).")
    if not num.isdigit():
        c.die("Numéro invalide.")
    if input(f"⚠ Le disque {num} sera TOTALEMENT EFFACÉ. Tape OUI pour confirmer : ").strip() != "OUI":
        c.die("Annulé.")

    dp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, newline="\r\n")
    dp.write(f"select disk {num}\nclean\nconvert gpt\ncreate partition primary\n"
             f"format fs=fat32 quick label=EFIBOOT\nassign\nexit\n")
    dp.close()
    r = subprocess.run(["diskpart", "/s", dp.name], capture_output=True, text=True)
    if r.returncode != 0:
        c.warn(r.stdout + r.stderr)
        c.die("diskpart a échoué (lance en Administrateur ?).")

    letter = _ps(f"(Get-Partition -DiskNumber {num} | Get-Volume | "
                 "Where-Object DriveLetter).DriveLetter").stdout.strip()
    if not letter:
        c.die("Lettre de lecteur introuvable après formatage.")
    dest = Path(f"{letter}:/")
    for item in stage.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
    c.ok(f"Clé USB {letter}: prête (bootable OpenCore + recovery).")
    return dest


# --------------------------------------------------------------------------- dispatch
def build(ver_key: str):
    if c.IS_LINUX or c.IS_MACOS:
        return _build_linux(ver_key)
    if c.IS_WINDOWS:
        return _build_windows(ver_key)
    c.die("OS non supporté pour la fabrication d'image.")
