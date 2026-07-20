"""eh.opencore — récupère OpenCorePkg (EFI, ocvalidate, macserial) + macrecovery."""
from __future__ import annotations

import stat
import zipfile
from pathlib import Path

from . import common as c


def _oc_dir() -> Path:
    return c.TOOLS / "OpenCore"


def fetch_opencore() -> Path:
    c.title("OpenCorePkg (EFI, ocvalidate, macserial)")
    d = _oc_dir()
    if (d / "X64" / "EFI" / "OC").is_dir():
        c.ok(f"OpenCorePkg déjà présent ({d})")
    else:
        url = c.gh_latest_asset("acidanthera/OpenCorePkg", r"OpenCore-.*-RELEASE\.zip")
        if not url:
            c.die("URL OpenCorePkg introuvable")
        c.log(f"Téléchargement : {url.rsplit('/', 1)[-1]}")
        zp = c.TOOLS / "opencore.zip"
        c.fetch_file(url, zp)
        if d.exists():
            import shutil
            shutil.rmtree(d)
        with zipfile.ZipFile(zp) as z:
            z.extractall(d)
        if not (d / "X64" / "EFI" / "OC").is_dir():
            c.die("Extraction OpenCorePkg échouée")
        c.ok("OpenCorePkg extrait")

    # macrecovery.py (pas toujours dans la release → master)
    mr = c.TOOLS / "macrecovery.py"
    if not mr.exists():
        c.fetch_file(
            "https://raw.githubusercontent.com/acidanthera/OpenCorePkg/master/"
            "Utilities/macrecovery/macrecovery.py", mr)
    c.ok("Outils OpenCore prêts")
    return d


def _find(name_options: list[str]) -> Path | None:
    for name in name_options:
        for p in _oc_dir().rglob(name):
            return p
    return None


def sample_plist() -> Path:
    p = _find(["Sample.plist"])
    if not p:
        c.die("Sample.plist introuvable (lance la récupération OpenCore)")
    return p


def macserial() -> Path | None:
    # binaire adapté à l'OS courant
    names = ["macserial.exe"] if c.IS_WINDOWS else (
        ["macserial.linux"] if c.IS_LINUX else ["macserial"])
    p = _find(names) or _find(["macserial"])
    if p and not c.IS_WINDOWS:
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def ocvalidate() -> Path | None:
    names = ["ocvalidate.exe"] if c.IS_WINDOWS else (
        ["ocvalidate.linux"] if c.IS_LINUX else ["ocvalidate"])
    p = _find(names) or _find(["ocvalidate"])
    if p and not c.IS_WINDOWS:
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def base_efi() -> Path:
    return _oc_dir() / "X64" / "EFI"


def macrecovery_py() -> Path:
    p = c.TOOLS / "macrecovery.py"
    if not p.exists():
        c.die("macrecovery.py absent")
    return p
