"""eh.efi — assemble l'EFI OpenCore, génère et valide le config.plist."""
from __future__ import annotations

import base64
import os
import plistlib
import shutil
import subprocess
import uuid
from pathlib import Path

from . import common as c
from . import opencore

_KEEP_DRIVERS = {"OpenRuntime.efi", "OpenCanopy.efi", "ResetNvramEntry.efi",
                  "OpenPartitionDxe.efi"}  # requis pour partitionner le DMG recovery monté (APFS)


def build_tree() -> None:
    c.title("Assemblage de l'EFI OpenCore")
    base = opencore.base_efi()
    if not (base / "OC").is_dir():
        c.die("EFI de base OpenCorePkg introuvable")
    if c.EFI.exists():
        shutil.rmtree(c.EFI)
    c.EFI.mkdir(parents=True)
    shutil.copytree(base / "BOOT", c.EFI / "BOOT")
    shutil.copytree(base / "OC", c.EFI / "OC")
    (c.EFI / "OC" / "Kexts").mkdir(exist_ok=True)
    (c.EFI / "OC" / "ACPI").mkdir(exist_ok=True)
    drv = c.EFI / "OC" / "Drivers"
    for f in drv.glob("*.efi"):
        if f.name not in _KEEP_DRIVERS:
            f.unlink()
    c.ok("Arborescence EFI copiée")


# --------------------------------------------------------------------------- SMBIOS
def _smbios_model(arch: str, chassis: str) -> str:
    desktop = {
        "haswell": "iMac15,1", "broadwell": "iMac16,2", "skylake": "iMac17,1",
        "kaby-lake": "iMac18,3", "coffee-lake": "iMac19,1",
        "comet-ice-lake": "iMac20,1", "rocket-tiger-lake": "iMacPro1,1",
        "alder-lake": "MacPro7,1", "raptor-lake": "MacPro7,1", "amd-ryzen": "MacPro7,1",
    }
    laptop = {
        "haswell": "MacBookPro11,1", "broadwell": "MacBookPro12,1",
        "skylake": "MacBookPro13,1", "kaby-lake": "MacBookPro14,1",
        "coffee-lake": "MacBookPro15,1", "comet-ice-lake": "MacBookPro16,1",
        "rocket-tiger-lake": "MacBookPro16,1", "alder-lake": "MacBookPro16,1",
        "raptor-lake": "MacBookPro16,1",
    }
    return (laptop if chassis == "laptop" else desktop).get(arch, "iMacPro1,1")


def _gen_smbios(model: str):
    serial = mlb = ""
    ms = opencore.macserial()
    if ms:
        try:
            out = subprocess.run([str(ms), "--model", model, "--generate", "--num", "1"],
                                 capture_output=True, text=True).stdout.strip()
            line = out.splitlines()[0] if out else ""
            if "|" in line:
                serial, mlb = (p.strip() for p in line.split("|")[:2])
        except OSError:
            pass
    return serial, mlb, str(uuid.uuid4()).upper(), os.urandom(6)


# --------------------------------------------------------------------------- Kexts
def _kext_meta(kdir: Path):
    info = kdir / "Contents" / "Info.plist"
    if not info.exists():
        return "", ""
    pl = plistlib.loads(info.read_bytes())
    exe = pl.get("CFBundleExecutable", "")
    return (f"Contents/MacOS/{exe}" if exe else ""), pl.get("CFBundleIdentifier", "")


def _kext_key(name: str):
    n = name.lower()
    if n == "lilu.kext":
        return (0, name)
    if n == "virtualsmc.kext":
        return (1, name)
    if n.startswith("smc"):
        return (2, name)
    return (3, name)


def _acpi_entries():
    acpi_dir = c.EFI / "OC" / "ACPI"
    entries = []
    for f in sorted(acpi_dir.glob("*.aml")):
        entries.append({"Comment": f.name, "Enabled": True, "Path": f.name})
    return entries


def _kext_entries():
    entries = []
    names = sorted((p.name for p in c.KEXTS.glob("*.kext")), key=_kext_key)
    for name in names:
        exec_path, bundle_id = _kext_meta(c.KEXTS / name)
        entries.append({
            "Arch": "x86_64", "BundlePath": name, "Comment": bundle_id,
            "Enabled": True, "ExecutablePath": exec_path,
            "MaxKernel": "", "MinKernel": "", "PlistPath": "Contents/Info.plist",
        })
    return entries


# --------------------------------------------------------------------------- Quirks
def _apply_quirks(cfg: dict, arch: str, family: str) -> None:
    cfg["Booter"]["Quirks"].update({
        "AvoidRuntimeDefrag": True, "DevirtualiseMmio": True,
        "EnableWriteUnprotector": False, "ProtectUefiServices": True,
        "RebuildAppleMemoryMap": True, "SetupVirtualMap": True,
        "SyncRuntimePermissions": True,
    })
    kq = cfg["Kernel"]["Quirks"]
    kq.update({"DisableIoMapper": True, "PanicNoKextDump": True,
               "PowerTimeoutKernelPanic": True})
    if arch in ("haswell", "broadwell", "skylake", "kaby-lake"):
        kq["AppleXcpmCfgLock"] = True
    if family == "amd":
        kq["ProvideCurrentCpuInfo"] = True


_FORCE_ENABLE_DRIVERS = {"OpenRuntime.efi", "OpenPartitionDxe.efi"}


def _sync_uefi_drivers(cfg: dict) -> None:
    """Le Sample.plist référence des drivers que build_tree() a retirés du
    dossier Drivers (dont l'ancien nom HfsPlus.efi) : n'active que ceux
    réellement présents, sinon OpenCore plante au boot en "cannot be found".
    OpenPartitionDxe.efi est désactivé par défaut dans le Sample alors qu'il
    est requis pour partitionner le DMG recovery monté (sinon "OCB: Failed to
    get bootable file off DMG" — le conteneur APFS n'est jamais exposé)."""
    present = {f.name for f in (c.EFI / "OC" / "Drivers").glob("*.efi")}
    for d in cfg["UEFI"]["Drivers"]:
        path = d.get("Path")
        if path not in present:
            d["Enabled"] = False
        elif path in _FORCE_ENABLE_DRIVERS:
            d["Enabled"] = True


def generate_config(hw: dict) -> None:
    c.title("Génération du config.plist")
    cfg = plistlib.loads(opencore.sample_plist().read_bytes())
    arch, family = hw.get("cpu_arch", "unknown"), hw.get("cpu_family", "unknown")
    chassis = hw.get("chassis", "desktop")

    cfg["Kernel"]["Add"] = _kext_entries()
    cfg["ACPI"]["Add"] = _acpi_entries()
    _apply_quirks(cfg, arch, family)
    _sync_uefi_drivers(cfg)

    boot_args = f"-v keepsyms=1 debug=0x100 alcid={hw.get('audio_layout', 1)}"
    if str(hw.get("dgpu", "")).startswith("amd:"):
        boot_args += " agdpmod=pikera"
    if family == "amd":
        boot_args += " npci=0x2000"
    guid = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
    nv = cfg["NVRAM"]["Add"].setdefault(guid, {})
    nv["boot-args"] = boot_args
    nv["csr-active-config"] = b"\x00\x00\x00\x00"   # SIP activé
    nv["prev-lang:kbd"] = b"fr:1"

    cfg["UEFI"]["APFS"]["JumpstartHotPlug"] = True  # sinon "LoadImage failed - Unsupported"
                                                     # au boot du DMG recovery (monté en ramdisk)

    sec = cfg["Misc"]["Security"]
    sec["SecureBootModel"], sec["Vault"] = "Disabled", "Optional"
    # ScanPolicy=0 (illimité) fait remonter dans le picker les OS déjà
    # installés sur le disque interne de la machine cible, en plus de la
    # recovery macOS du support de boot — d'où l'idée d'ajouter
    # OC_SCAN_DEVICE_LOCK (0x2) pour ne garder que le support USB. Mais
    # OC_SCAN_DEVICE_LOCK CASSE le boot du DMG recovery : le conteneur APFS
    # *virtuel* exposé par Jumpstart au chargement du DMG en RAM a un device
    # path synthétique (VenHw/MemoryMapped) qu'OcGetDevicePolicyType ne sait
    # classer dans AUCUN type de bus (SATA/USB/NVMe/PCI...) — c'est un FIXME
    # connu du code source d'OpenCorePkg (Library/OcBootManagementLib/
    # PolicyManagement.c, réf. acidanthera/bugtracker#335, "RamDisk exception
    # non gérée") : la fonction renvoie 0, et 0 & N'IMPORTE-QUEL-bit vaut
    # toujours 0 → "OCJS: Cannot connect, Policy error" puis "OCB: LoadImage
    # failed - Unsupported", quels que soient les bits ajoutés (USB, PCI...
    # testés, aucun ne suffit). Confirmé en rejouant le boot en QEMU (build
    # DEBUG d'OpenCore, USB émulé) : log identique au blocage vu sur le N100
    # réel. Seule option : ne PAS activer DeviceLock. On garde uniquement
    # FileSystemLock (0x1) + APFS (0x100, requis par UEFI>APFS>EnableJumpstart)
    # + ESP (0x400, partition FAT où vit com.apple.recovery.boot/, cf
    # image.py) : ça filtre les autres systèmes de fichiers (NTFS, etc.) mais
    # PAS par device — un macOS déjà installé sur le disque interne (APFS
    # lui aussi) redeviendrait visible dans le picker. Compromis accepté :
    # un picker qui boote > un picker propre qui ne boote pas.
    sec["ScanPolicy"] = 0x1 | 0x100 | 0x400
    cfg["Misc"]["Boot"]["Timeout"] = 5
    cfg["Misc"]["Boot"]["ShowPicker"] = True

    model = _smbios_model(arch, chassis)
    serial, mlb, smuuid, rom = _gen_smbios(model)
    pi = cfg["PlatformInfo"]
    pi["UpdateSMBIOS"], pi["UpdateSMBIOSMode"] = True, "Create"
    g = pi["Generic"]
    g["SystemProductName"] = model
    g["SystemSerialNumber"] = serial or g.get("SystemSerialNumber", "")
    g["MLB"] = mlb or g.get("MLB", "")
    g["SystemUUID"] = smuuid
    g["ROM"] = rom

    out = c.EFI / "OC" / "config.plist"
    out.write_bytes(plistlib.dumps(cfg))
    c.ok(f"config.plist écrit ({model}, serial {serial or 'n/a'}, "
         f"{len(cfg['Kernel']['Add'])} kexts, boot-args '{boot_args}')")


def validate() -> None:
    c.title("Validation (ocvalidate)")
    ocv = opencore.ocvalidate()
    if not ocv:
        c.warn("ocvalidate absent — validation ignorée")
        return
    r = subprocess.run([str(ocv), str(c.EFI / "OC" / "config.plist")],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode == 0 and "No issues found" in r.stdout:
        c.ok("config.plist valide")
    else:
        c.warn("ocvalidate a relevé des problèmes — à corriger avant boot réel")
