# easy-hackintosh 🍏

*[English version →](README.en.md)*

Génère **automatiquement** un installeur macOS bootable et un dossier
**EFI OpenCore** adapté au matériel de ta machine. **Linux et Windows.**

Un seul outil (Python) :

1. **demande la version** de macOS (High Sierra → Tahoe) ;
2. **télécharge la recovery** Apple (via `macrecovery`) ;
3. **scanne tout le matériel** (CPU, iGPU/dGPU, Ethernet, Wi-Fi, codec audio, NVMe) ;
4. **installe les kexts** correspondants (Lilu, VirtualSMC, WhateverGreen, AppleALC…) ;
5. **génère un `config.plist`** OpenCore (quirks + SMBIOS adaptés) ;
6. le **valide avec `ocvalidate`** ;
7. **fabrique le support bootable** : image disque (Linux, clé USB ou VM QEMU) ou
   écriture directe sur clé USB (Windows).

## Installation en une ligne

**Linux :**

```bash
curl -fsSL https://raw.githubusercontent.com/devfrp/easy-hackintosh/main/get.sh | sh
```

**Windows** (PowerShell ; console *Administrateur* pour l'écriture USB) :

```powershell
irm https://raw.githubusercontent.com/devfrp/easy-hackintosh/main/get.ps1 | iex
```

### Ou manuellement

```bash
git clone https://github.com/devfrp/easy-hackintosh.git
cd easy-hackintosh
python3 easy_hackintosh.py          # Windows : python easy_hackintosh.py
```

### Dépendances

- **Windows** : Python 3 + Git (installés par `get.ps1` via winget si absents).
  Le reste (partitionnement, formatage) utilise `diskpart`, fourni avec Windows.
- **Linux** : Python 3 + `mtools` + `gptfdisk`/`util-linux` + `pciutils` `usbutils`,
  et `qemu` + `edk2-ovmf` pour tester en VM. Sur Arch :

```bash
sudo pacman -S --needed python mtools gptfdisk pciutils usbutils qemu-full edk2-ovmf
```

## Usage

```bash
python3 easy_hackintosh.py          # assistant complet : version → support bootable
python3 easy_hackintosh.py scan     # scan matériel seul (→ build/hardware.json)
python3 easy_hackintosh.py efi      # régénère seulement l'EFI (kexts + config)
python3 easy_hackintosh.py image    # refabrique le support depuis l'EFI existant
```

Sélection non interactive : `EH_VERSION=sequoia python3 easy_hackintosh.py`.

### Résultat

Tout est écrit dans `build/` (efface `build/` pour repartir de zéro) :

| Fichier | Contenu |
|---|---|
| `build/out/macOS-<version>.iso` | ISO bootable hybride, un seul fichier (Linux : USB ou QEMU) |
| `build/EFI/` | Dossier EFI OpenCore généré |
| `build/out/run-qemu.sh` | Lance l'ISO dans une VM (Linux) |
| `build/hardware.json` | Résultat du scan matériel |

**Tester en VM (Linux) :** `build/out/run-qemu.sh`

**Écrire sur USB (Linux)** — ⚠️ efface la clé, vérifie `/dev/sdX` :

```bash
sudo dd if=build/out/macOS-*.iso of=/dev/sdX bs=4M oflag=sync status=progress
```

**Windows** : le script détecte les clés USB, demande confirmation (`OUI`), puis
formate en GPT/FAT32 et copie l'EFI + la recovery via `diskpart`.

## ⚠️ À savoir (honnêteté)

- **Installeur « recovery » en ligne** : macOS est téléchargé pendant l'installation
  (connexion requise). Un installeur complet hors-ligne exige `createinstallmedia`,
  qui n'existe que sous macOS.
- **Automatisé à la compilation** : SSDT ACPI universels *boot-safe*
  ([Dortania](https://github.com/dortania/Getting-Started-With-ACPI) : EC, USBX, AWAC,
  plugin-type, PNLF), **USB** via `SSDT-RHUB` (ré-énumère tous les ports), et **Wi-Fi**
  (kext Intel `AirportItlwm` choisi selon la version, ou Broadcom `AirportBrcmFixup`).
- L'EFI reste un **point de départ**, pas un config parfait clé en main. Aucun outil ne
  garantit un boot du premier coup. Réglages optionnels/avancés :
  - **Mapping USB précis** (limite de 15 ports par contrôleur) → USBToolBox sous Windows ;
  - **Wi-Fi Intel sous Sequoia/Tahoe** : pas encore de build stable → build Sonoma en repli, à vérifier ;
  - ACPI très spécifique → SSDTTime + [guide Dortania](https://dortania.github.io/OpenCore-Install-Guide/).
- **Tahoe (26)** : dernière version macOS à supporter Intel, mais **seulement 4 modèles réels**
  (MacPro7,1, MacBookPro16,1/16,2, iMac20,1/20,2) — l'installeur macOS refuse le SMBIOS
  spoofé s'il ne matche pas un de ces modèles. macOS 27 sera Apple Silicon uniquement.
- Les **laptops** sont plus délicats (batterie, veille, Wi-Fi, USB).

## Matériel géré automatiquement

| Composant | Détection → kext / SSDT |
|---|---|
| Intel iGPU / AMD dGPU | WhateverGreen |
| Audio (Realtek ALC…) | AppleALC + `layout-id` de départ |
| Ethernet Intel / Realtek | IntelMausi / RealtekRTL8111 / LucyRTL8125 |
| Wi-Fi Intel / Broadcom | AirportItlwm (selon version) / AirportBrcmFixup |
| USB | SSDT-RHUB (ré-énumération des ports) |
| ACPI (EC, horloge, CPU, backlight) | SSDT-EC/USBX, SSDT-AWAC, SSDT-PLUG, SSDT-PNLF |
| NVMe | NVMeFix |
| SMC (obligatoire) | VirtualSMC + plugins |

## Crédits

Repose sur [OpenCorePkg](https://github.com/acidanthera/OpenCorePkg), les kexts
[Acidanthera](https://github.com/acidanthera) et le
[guide Dortania](https://dortania.github.io/OpenCore-Install-Guide/).
Aucun binaire macOS n'est redistribué.
