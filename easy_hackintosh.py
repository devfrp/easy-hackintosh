#!/usr/bin/env python3
"""easy-hackintosh — génère un installeur macOS + EFI OpenCore adapté au matériel.

Cross-platform (Linux et Windows). Un seul outil :
  demande la version → télécharge la recovery → scanne le matos →
  installe les kexts → génère+valide le config.plist → fabrique le support bootable.

Usage :
  python3 easy_hackintosh.py            # assistant complet
  python3 easy_hackintosh.py scan       # scan matériel seul
  python3 easy_hackintosh.py efi        # régénère seulement l'EFI (kexts + config)
  python3 easy_hackintosh.py image      # refabrique le support depuis l'EFI existant

Sélection non interactive : EH_VERSION=<clé> (ex: sequoia, sonoma, ventura…).
Tout est écrit dans ./build (supprime ce dossier pour repartir de zéro).
"""
from __future__ import annotations

import sys

from eh import common as c
from eh import acpi, deps, download, efi, hwscan, image, opencore

BANNER = r"""
  ___  __ _ ____ _  _    _  _ ____ ____ _  _ ___ _ _  _ ____ ____ _  _
  |__] |  |  ___| |  |    |__| |__| |     |/   |  | |\ |  |  |  | [__ |__|
  |___ |__| ____| |__|    |  | |  | |___  |\   |  | | \|  |  |__| ___]|  |
      installeur macOS + EFI OpenCore automatique  (Linux / Windows)
"""


def _summary(img) -> None:
    c.title("Terminé")
    print(f"Support     : {img or '(non généré)'}")
    print(f"EFI généré  : {c.EFI}")
    print(f"Matériel    : {c.HWENV}")
    if c.IS_LINUX:
        print(f"\nTester en VM : {c.OUT / 'run-qemu.sh'}")
        print("Écrire USB   : sudo dd if=<image> of=/dev/sdX bs=4M oflag=sync status=progress")
    print("\nAuto inclus : SSDT ACPI (dont USB/RHUB), kexts, Wi-Fi (Intel/Broadcom).")
    print("Optionnel : mapping USB *précis* (limite 15 ports) via USBToolBox sous Windows.")
    c.warn("EFI de DÉPART : boot non garanti tel quel. À valider/ajuster (guide Dortania).")


def run_full() -> None:
    print(BANNER)
    c.ensure_dirs()
    deps.check()
    opencore.fetch_opencore()
    ver = download.version_from_env() or download.choose_version()
    _save_version(ver["key"])
    # Le gros téléchargement (~1 Go) démarre dès la sélection, en arrière-plan,
    # pendant qu'on scanne le matériel et qu'on prépare l'EFI.
    rec = download.start_recovery(ver)
    try:
        hw = hwscan.scan()
        efi.build_tree()
        acpi.install(hw)                 # SSDT USB/ACPI boot-safe
        kexts_install(hw, ver["key"])    # kexts + Wi-Fi auto
        efi.generate_config(hw)
        efi.validate()
    except BaseException:
        rec.proc.terminate()
        raise
    rec.wait()               # on n'attend qu'ici, juste avant de fabriquer l'image
    img = image.build(ver["key"])
    _summary(img)


def _save_version(key: str) -> None:
    (c.BUILD / "version.txt").write_text(key)


def _load_version() -> str | None:
    import os
    p = c.BUILD / "version.txt"
    return os.environ.get("EH_VERSION") or (p.read_text().strip() if p.exists() else None)


def kexts_install(hw: dict, ver_key: str | None = None) -> None:
    from eh import kexts
    kexts.install(hw, ver_key)


def run_scan() -> None:
    print(BANNER)
    c.ensure_dirs()
    hwscan.scan()


def run_efi() -> None:
    print(BANNER)
    c.ensure_dirs()
    opencore.fetch_opencore()
    hw = hwscan.load()
    ver_key = _load_version()
    efi.build_tree()
    acpi.install(hw)
    kexts_install(hw, ver_key)
    efi.generate_config(hw)
    efi.validate()
    c.ok(f"EFI régénéré : {c.EFI}")


def run_image() -> None:
    print(BANNER)
    c.ensure_dirs()
    if not (c.EFI / "OC").exists():
        c.die("Aucun EFI généré — lance d'abord 'efi' ou l'assistant complet.")
    img = image.build("installer")
    _summary(img)


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "full"
    try:
        if cmd in ("full", ""):
            run_full()
        elif cmd == "scan":
            run_scan()
        elif cmd == "efi":
            run_efi()
        elif cmd == "image":
            run_image()
        elif cmd in ("-h", "--help"):
            print(__doc__)
        else:
            c.err(f"argument inconnu : {cmd} (voir --help)")
            return 2
    except c.EHError as e:
        c.err(str(e))
        return 1
    except KeyboardInterrupt:
        c.err("Interrompu.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
