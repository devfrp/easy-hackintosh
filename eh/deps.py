"""eh.deps — vérifie les outils système requis selon l'OS."""
from __future__ import annotations

import shutil

from . import common as c

_LINUX_CMDS = ["mformat", "mcopy", "xorriso", "lspci", "lsusb"]
_WIN_CMDS = ["powershell", "diskpart"]

_HINT = {
    "arch": "sudo pacman -S --needed dosfstools libisoburn mtools pciutils usbutils qemu-full edk2-ovmf",
    "debian": "sudo apt-get install -y dosfstools xorriso mtools pciutils usbutils qemu-system-x86 ovmf",
    "fedora": "sudo dnf install -y dosfstools xorriso mtools pciutils usbutils qemu-system-x86 edk2-ovmf",
}


def _distro_hint() -> str:
    if shutil.which("pacman"):
        return _HINT["arch"]
    if shutil.which("apt-get"):
        return _HINT["debian"]
    if shutil.which("dnf"):
        return _HINT["fedora"]
    return "installe : mtools gptfdisk pciutils usbutils qemu ovmf"


def check() -> None:
    c.title("Dépendances système")
    cmds = _WIN_CMDS if c.IS_WINDOWS else _LINUX_CMDS
    missing = [x for x in cmds if not shutil.which(x)]
    if not missing:
        c.ok("Outils système présents")
        return
    c.warn(f"Manquant : {', '.join(missing)}")
    if c.IS_WINDOWS:
        c.die("PowerShell/diskpart requis (fournis avec Windows).")
    print("  " + _distro_hint())
    c.die("Installe les paquets ci-dessus puis relance.")
