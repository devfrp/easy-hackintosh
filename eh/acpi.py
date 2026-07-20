"""eh.acpi — installe des SSDT universels précompilés (boot-safe) selon la plateforme.

Approche : plutôt que d'analyser la DSDT (nécessite root + un outil interactif),
on télécharge les SSDT prêts-à-l'emploi et *context-aware* du dépôt Dortania
(Getting-Started-With-ACPI). Ils s'auto-désactivent si le matériel ne correspond
pas → pas de risque de boot. Couvre notamment le USB (SSDT-RHUB ré-énumère les ports),
l'horloge (AWAC/RTC), le plugin-type CPU, l'EC, et le rétroéclairage laptop.
"""
from __future__ import annotations

from . import common as c

_BASE = ("https://raw.githubusercontent.com/dortania/Getting-Started-With-ACPI/"
         "master/extra-files/compiled/")

# arch avec horloge AWAC (300-series et plus récent)
_AWAC_ARCHS = {"skylake", "kaby-lake", "coffee-lake", "comet-ice-lake",
               "rocket-tiger-lake", "alder-lake", "raptor-lake", "amd-ryzen"}
# arch "legacy" sans USBX (SMBIOS Haswell/Broadwell)
_NO_USBX = {"haswell", "broadwell"}


def _select(hw: dict) -> list[str]:
    arch = hw.get("cpu_arch", "unknown")
    laptop = hw.get("chassis") == "laptop"
    ssdts = ["SSDT-RHUB.aml"]                    # USB : ré-énumère tous les ports

    if arch in _NO_USBX:
        ssdts.append("SSDT-EC-LAPTOP.aml" if laptop else "SSDT-EC-DESKTOP.aml")
    else:
        ssdts.append("SSDT-EC-USBX-LAPTOP.aml" if laptop else "SSDT-EC-USBX-DESKTOP.aml")

    if hw.get("cpu_family") == "intel":
        ssdts.append("SSDT-PLUG-DRTNIA.aml")     # plugin-type CPU (power management)
    if arch in _AWAC_ARCHS:
        ssdts.append("SSDT-AWAC.aml")            # horloge context-aware
    if laptop:
        ssdts.append("SSDT-PNLF.aml")            # rétroéclairage écran

    return ssdts


def install(hw: dict) -> list[str]:
    c.title("ACPI (SSDT universels boot-safe)")
    dest = c.EFI / "OC" / "ACPI"
    dest.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    for name in _select(hw):
        try:
            c.fetch_file(_BASE + name, dest / name)
            installed.append(name)
            c.ok(f"SSDT : {name}")
        except Exception as e:  # noqa: BLE001
            c.warn(f"SSDT {name} non récupéré : {e}")
    c.warn("Mapping USB *précis* (limite 15 ports) : optionnel, via USBToolBox sous Windows.")
    c.ok(f"{len(installed)} SSDT installés")
    return installed
