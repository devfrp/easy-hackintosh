"""eh.common — helpers partagés (chemins, logs, réseau, GitHub), cross-platform."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

IS_WINDOWS = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"

# --- Chemins (relatifs à la racine du projet) -------------------------------
ROOT = Path(__file__).resolve().parent.parent
BUILD = Path(os.environ.get("EH_BUILD", ROOT / "build"))
TOOLS = BUILD / "tools"
EFI = BUILD / "EFI"
RECOVERY = BUILD / "recovery"
KEXTS = EFI / "OC" / "Kexts"
HWENV = BUILD / "hardware.json"
OUT = BUILD / "out"


def ensure_dirs() -> None:
    for d in (BUILD, TOOLS, OUT):
        d.mkdir(parents=True, exist_ok=True)


# --- Logs colorés (désactivés si pas un TTY) --------------------------------
_TTY = sys.stdout.isatty()
if _TTY and not IS_WINDOWS:
    _C = dict(r="\033[0m", b="\033[1m", red="\033[31m", grn="\033[32m",
              ylw="\033[33m", blu="\033[34m", cyn="\033[36m")
else:  # Windows console / pipe : pas de codes ANSI
    _C = dict(r="", b="", red="", grn="", ylw="", blu="", cyn="")


def log(msg: str) -> None:   print(f"{_C['cyn']}::{_C['r']} {msg}")
def ok(msg: str) -> None:    print(f"{_C['grn']}[ok]{_C['r']} {msg}")
def warn(msg: str) -> None:  print(f"{_C['ylw']}[!]{_C['r']} {msg}", file=sys.stderr)
def err(msg: str) -> None:   print(f"{_C['red']}[x]{_C['r']} {msg}", file=sys.stderr)
def title(msg: str) -> None: print(f"\n{_C['b']}{_C['blu']}=== {msg} ==={_C['r']}")


class EHError(Exception):
    """Erreur métier (message clair pour l'utilisateur)."""


def die(msg: str) -> "None":
    raise EHError(msg)


# --- Réseau -----------------------------------------------------------------
_UA = {"User-Agent": "easy-hackintosh"}


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fetch_file(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 16):
            f.write(chunk)
    return dest


def gh_latest_asset(repo: str, pattern: str) -> str | None:
    """URL du 1ᵉʳ asset de la dernière release de owner/repo dont le nom matche `pattern`."""
    data = json.loads(fetch_bytes(f"https://api.github.com/repos/{repo}/releases/latest"))
    rx = re.compile(pattern)
    for a in data.get("assets", []):
        if rx.search(a["name"]):
            return a["browser_download_url"]
    return None
