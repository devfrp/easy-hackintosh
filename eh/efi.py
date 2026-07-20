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
                  "OpenPartitionDxe.efi", "OpenHfsPlus.efi"}
# OpenPartitionDxe : requis pour partitionner le DMG recovery monté.
# OpenHfsPlus : le volume à l'intérieur de BaseSystem.dmg est en réalité
# HFS+ (vérifié en décompressant le DMG avec `qemu-img convert -f dmg`,
# signature "H+" à l'offset standard 1024 — PAS de conteneur APFS/NXSB
# nulle part dans l'image). Toute la piste APFS/Jumpstart suivie
# précédemment était une fausse piste : le vrai bloquant est l'absence du
# driver HFS+ (voir _sync_uefi_drivers ci-dessous).


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
        # Firmwares OEM bon marché (mini-PC génériques type N100) mentent sur
        # la memory map remise à ExitBootServices : le premier appel échoue et
        # OpenCore reste bloqué juste après "LOG:EXITBS:START" (testé sur N100
        # réel, 2026-07-20). ForceExitBootServices force un retry avec une
        # map réduite, ProtectMemoryRegions protège les zones RT contre la
        # corruption par ce même firmware bugué.
        "ForceExitBootServices": True, "ProtectMemoryRegions": True,
    })
    kq = cfg["Kernel"]["Quirks"]
    kq.update({"DisableIoMapper": True, "PanicNoKextDump": True,
               "PowerTimeoutKernelPanic": True})
    if arch in ("haswell", "broadwell", "skylake", "kaby-lake"):
        kq["AppleXcpmCfgLock"] = True
    if family == "amd":
        kq["ProvideCurrentCpuInfo"] = True


_FORCE_ENABLE_DRIVERS = {"OpenRuntime.efi", "OpenPartitionDxe.efi", "OpenHfsPlus.efi"}
# Sample.plist référence encore l'ancien nom du driver HFS+ ("HfsPlus.efi"),
# renommé "OpenHfsPlus.efi" dans les releases OpenCorePkg récentes — sans ce
# renommage, _sync_uefi_drivers ne le retrouve jamais dans `present` et le
# désactive silencieusement.
_RENAME_DRIVERS = {"HfsPlus.efi": "OpenHfsPlus.efi"}


def _sync_uefi_drivers(cfg: dict) -> None:
    """Le Sample.plist référence des drivers que build_tree() a retirés du
    dossier Drivers, sous leur ancien nom pour certains (HfsPlus.efi) : on
    corrige le nom puis n'active que ceux réellement présents, sinon
    OpenCore plante au boot en "cannot be found".
    OpenPartitionDxe.efi est désactivé par défaut dans le Sample alors qu'il
    est requis pour partitionner le DMG recovery monté (sinon "OCB: Failed to
    get bootable file off DMG"). OpenHfsPlus.efi est nécessaire car le volume
    dans BaseSystem.dmg est HFS+ (vérifié par décompression du DMG), pas
    APFS : sans ce driver, aucun SimpleFileSystemProtocol n'est exposé pour
    la partition et OpenCore échoue avec "LoadImage failed - Unsupported"."""
    present = {f.name for f in (c.EFI / "OC" / "Drivers").glob("*.efi")}
    for d in cfg["UEFI"]["Drivers"]:
        path = _RENAME_DRIVERS.get(d.get("Path"), d.get("Path"))
        d["Path"] = path
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

    # Le volume dans BaseSystem.dmg est HFS+, pas APFS (cf ScanPolicy
    # ci-dessous) : Jumpstart ne sert à rien ici, on le désactive pour éviter
    # l'avertissement ocvalidate "EnableJumpstart enabled but ScanPolicy does
    # not allow APFS scanning" plutôt que de rouvrir le bit APFS pour rien.
    cfg["UEFI"]["APFS"]["EnableJumpstart"] = False

    sec = cfg["Misc"]["Security"]
    sec["SecureBootModel"], sec["Vault"] = "Disabled", "Optional"
    # Le volume à l'intérieur de BaseSystem.dmg est HFS+, pas APFS (confirmé
    # en décompressant le DMG avec qemu-img : signature "H+" à l'offset
    # standard, aucun NXSB nulle part). ScanPolicy doit donc autoriser le
    # filesystem HFS (bit OC_SCAN_ALLOW_FS_HFS = 0x200), qui manquait
    # complètement jusqu'ici — la piste APFS/Jumpstart/DeviceLock creusée
    # avant (cf historique des commits ScanPolicy) était une fausse piste :
    # même avec DeviceLock retiré, un ScanPolicy sans le bit HFS ne peut de
    # toute façon jamais faire remonter un volume HFS+ dans le picker. On
    # garde FileSystemLock (0x1) sans DeviceLock (0x2) — cf commit
    # 292b761 : le device path synthétique du DMG monté en RAM n'est
    # classable dans aucun bus connu par OcGetDevicePolicyType, DeviceLock
    # bloquerait donc tout systématiquement, indépendamment du filesystem.
    sec["ScanPolicy"] = 0x1 | 0x200 | 0x400
    cfg["Misc"]["Boot"]["Timeout"] = 5
    cfg["Misc"]["Boot"]["ShowPicker"] = True
    # HideAuxiliary=true (défaut Sample.plist) masque l'entrée recovery
    # macOS dans le picker (OpenCore la classe "auxiliaire", au même titre
    # que com.apple.installer) : il faudrait maintenir Espace pour la
    # révéler. On force false pour qu'elle soit visible d'office à côté de
    # Windows/Linux.
    cfg["Misc"]["Boot"]["HideAuxiliary"] = False

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
