"""eh.kexts — sélectionne et télécharge les kexts selon le matériel détecté."""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from . import common as c


def _dl_repo(repo: str) -> Path | None:
    dst = c.TOOLS / "kext-src" / repo.replace("/", "_")
    if dst.is_dir():
        return dst
    url = c.gh_latest_asset(repo, r".*-RELEASE\.zip")
    if not url:
        c.warn(f"release introuvable pour {repo}")
        return None
    dst.mkdir(parents=True, exist_ok=True)
    zp = dst / "pkg.zip"
    try:
        c.fetch_file(url, zp)
        with zipfile.ZipFile(zp) as z:
            z.extractall(dst)
    except Exception as e:  # noqa: BLE001
        c.warn(f"téléchargement/extraction {repo} échoué : {e}")
        return None
    return dst


def _copy_kext(src: Path, name: str) -> bool:
    for found in src.rglob(name):
        if found.is_dir():
            target = c.KEXTS / name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(found, target)
            c.ok(f"kext : {name}")
            return True
    c.warn(f"kext {name} introuvable dans {repo_short(src)}")
    return False


def repo_short(p: Path) -> str:
    return p.name


def _install_from(repo: str, *kexts: str) -> None:
    src = _dl_repo(repo)
    if not src:
        return
    for k in kexts:
        _copy_kext(src, k)


# Version macOS → sous-chaîne de l'asset AirportItlwm (OpenIntelWireless).
_ITLWM_ASSET = {
    "high-sierra": "HighSierra", "mojave": "Mojave", "catalina": "Catalina",
    "big-sur": "BigSur", "monterey": "Monterey", "ventura": "Ventura",
    "sonoma": "Sonoma14.4", "sequoia": "Sonoma14.4",  # pas encore de build Sequoia stable
    "tahoe": "Sonoma14.4",  # pas encore de build Tahoe stable
}


def _install_airportitlwm(ver_key: str | None) -> None:
    """Wi-Fi Intel : télécharge AirportItlwm correspondant à la version macOS."""
    key = ver_key or "sonoma"
    marker = _ITLWM_ASSET.get(key, "Sonoma14.4")
    if key in ("sequoia", "tahoe"):
        c.warn(f"Wi-Fi Intel : pas de build {key.capitalize()} stable → build Sonoma14.4 (à vérifier).")
    url = c.gh_latest_asset("OpenIntelWireless/itlwm",
                            rf"AirportItlwm.*{marker}.*\.kext\.zip")
    if not url:
        c.warn(f"AirportItlwm ({marker}) introuvable — Wi-Fi Intel à installer à la main.")
        return
    import zipfile
    dst = c.TOOLS / "kext-src" / f"AirportItlwm_{marker}"
    dst.mkdir(parents=True, exist_ok=True)
    zp = dst / "pkg.zip"
    try:
        c.fetch_file(url, zp)
        with zipfile.ZipFile(zp) as z:
            z.extractall(dst)
    except Exception as e:  # noqa: BLE001
        c.warn(f"AirportItlwm : téléchargement échoué : {e}")
        return
    _copy_kext(dst, "AirportItlwm.kext")


def install(hw: dict, ver_key: str | None = None) -> int:
    c.title("Kexts (selon le matériel détecté)")
    if c.KEXTS.exists():
        shutil.rmtree(c.KEXTS)
    c.KEXTS.mkdir(parents=True, exist_ok=True)

    # Socle obligatoire
    _install_from("acidanthera/Lilu", "Lilu.kext")
    vsmc = ["VirtualSMC.kext", "SMCProcessor.kext", "SMCSuperIO.kext"]
    if hw.get("chassis") == "laptop":
        vsmc += ["SMCBatteryManager.kext", "SMCLightSensor.kext"]
    _install_from("acidanthera/VirtualSMC", *vsmc)

    if hw.get("igpu") or hw.get("dgpu"):
        _install_from("acidanthera/WhateverGreen", "WhateverGreen.kext")
    if hw.get("audio_codec"):
        _install_from("acidanthera/AppleALC", "AppleALC.kext")

    eth = hw.get("eth_kext")
    if eth == "IntelMausi":
        _install_from("acidanthera/IntelMausi", "IntelMausi.kext")
    elif eth == "RealtekRTL8111":
        _install_from("Mieze/RTL8111_driver_for_OS_X", "RealtekRTL8111.kext")
    elif eth == "LucyRTL8125Ethernet":
        _install_from("Mieze/LucyRTL8125Ethernet", "LucyRTL8125Ethernet.kext")
    elif hw.get("eth"):
        c.warn("Ethernet non reconnu — ajoute le kext à la main")

    wifi = (hw.get("wifi") or "").lower()
    if hw.get("wifi_kext") == "AirportBrcmFixup":
        _install_from("acidanthera/AirportBrcmFixup", "AirportBrcmFixup.kext")
    elif "intel" in wifi:
        _install_airportitlwm(ver_key)
    elif hw.get("wifi"):
        c.warn("Wi-Fi non Intel/Broadcom — support limité, à voir à la main.")

    if hw.get("nvme"):
        _install_from("acidanthera/NVMeFix", "NVMeFix.kext")

    c.warn("Mapping USB non généré (USBToolBox/USBMap requis sous macOS après install).")
    n = len(list(c.KEXTS.glob("*.kext")))
    c.ok(f"{n} kext(s) installés dans {c.KEXTS}")
    return n
