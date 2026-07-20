"""eh.download — choix de la version macOS + téléchargement de la recovery."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import common as c
from . import opencore


def _boards() -> list[tuple[str, str, str, str]]:
    rows = []
    for line in (c.ROOT / "data" / "boards.conf").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, name, board, mlb = line.split("|")
        rows.append((key, name, board, mlb))
    return rows


def _version_number(name: str) -> str | None:
    """Extrait le numéro entre parenthèses d'un nom affiché (« Sonoma (14) » → « 14 »)."""
    if "(" in name and name.endswith(")"):
        return name.rsplit("(", 1)[1][:-1]
    return None


def choose_version() -> dict:
    c.title("Version de macOS à installer")
    rows = _boards()
    for i, (_, name, _, _) in enumerate(rows, 1):
        print(f"  {c._C['b']}{i:2}{c._C['r']}) {name}")
    while True:
        try:
            raw = input(f"Ton choix [1-{len(rows)}] (index, clé ou version macOS ex: 14) : ").strip()
        except EOFError:
            c.die("Entrée requise (mode non interactif). Utilise EH_VERSION=<clé>.")
        if raw.isdigit() and 1 <= int(raw) <= len(rows):
            key, name, board, mlb = rows[int(raw) - 1]
            break
        match = next((r for r in rows if raw.lower() in (r[0], _version_number(r[1]))), None)
        if match:
            key, name, board, mlb = match
            break
        c.warn("Entrée invalide.")
    board = os.environ.get("EH_BOARD_ID", board)
    mlb = os.environ.get("EH_MLB", mlb)
    c.ok(f"Choisi : {name} (board-id {board})")
    return {"key": key, "name": name, "board": board, "mlb": mlb}


def version_from_env() -> dict | None:
    """Sélection non interactive via EH_VERSION=<clé> (ex: sequoia)."""
    key = os.environ.get("EH_VERSION")
    if not key:
        return None
    for k, name, board, mlb in _boards():
        if k == key:
            return {"key": k, "name": name,
                    "board": os.environ.get("EH_BOARD_ID", board),
                    "mlb": os.environ.get("EH_MLB", mlb)}
    c.die(f"EH_VERSION inconnu : {key}")


class RecoveryJob:
    """Téléchargement macrecovery lancé en arrière-plan (dès le choix de version)."""

    def __init__(self, ver: dict):
        mr = opencore.macrecovery_py()
        if c.RECOVERY.exists():
            shutil.rmtree(c.RECOVERY)
        c.RECOVERY.mkdir(parents=True)
        self.log_path = c.RECOVERY / "download.log"
        self._log = open(self.log_path, "w")
        c.log(f"Recovery : téléchargement démarré en arrière-plan "
              f"(board-id={ver['board']}) → {self.log_path}")
        self.proc = subprocess.Popen(
            [sys.executable, str(mr), "-b", ver["board"], "-m", ver["mlb"],
             "-os", "default", "download"],
            cwd=c.RECOVERY, stdout=self._log, stderr=subprocess.STDOUT)

    def wait(self) -> Path:
        c.title("Attente de la fin du téléchargement recovery")
        rc = self.proc.wait()
        self._log.close()
        if rc != 0:
            c.warn(self.log_path.read_text()[-1500:])
            c.die("Téléchargement recovery échoué (connexion / board-id ?)")
        base = next(c.RECOVERY.rglob("BaseSystem.dmg"), None)
        if not base:
            c.die("BaseSystem.dmg introuvable après téléchargement")
        c.ok(f"Recovery récupérée → {base}")
        return base


def start_recovery(ver: dict) -> RecoveryJob:
    return RecoveryJob(ver)
