# easy-hackintosh 🍏

*[Version française →](README.md)*

**Automatically** builds a bootable macOS installer and a matching **OpenCore EFI**
folder for your hardware. **Linux and Windows.**

A single Python tool:

1. **asks which macOS version** (High Sierra → Tahoe);
2. **downloads Apple's recovery** (via `macrecovery`);
3. **scans all hardware** (CPU, iGPU/dGPU, Ethernet, Wi-Fi, audio codec, NVMe);
4. **installs matching kexts** (Lilu, VirtualSMC, WhateverGreen, AppleALC…);
5. **generates an OpenCore `config.plist`** (adapted quirks + SMBIOS);
6. **validates it with `ocvalidate`**;
7. **builds the bootable media**: disk image (Linux — USB stick or QEMU VM) or
   direct USB write (Windows).

## One-line install

**Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/devfrp/easy-hackintosh/main/get.sh | sh
```

**Windows** (PowerShell; use an *Administrator* console for USB writing):

```powershell
irm https://raw.githubusercontent.com/devfrp/easy-hackintosh/main/get.ps1 | iex
```

### Or manually

```bash
git clone https://github.com/devfrp/easy-hackintosh.git
cd easy-hackintosh
python3 easy_hackintosh.py          # Windows: python easy_hackintosh.py
```

### Dependencies

- **Windows**: Python 3 + Git (installed by `get.ps1` via winget if missing).
  Partitioning/formatting uses `diskpart`, shipped with Windows.
- **Linux**: Python 3 + `mtools` + `gptfdisk`/`util-linux` + `pciutils` `usbutils`,
  plus `qemu` + `edk2-ovmf` to test in a VM. On Arch:

```bash
sudo pacman -S --needed python mtools gptfdisk pciutils usbutils qemu-full edk2-ovmf
```

## Usage

```bash
python3 easy_hackintosh.py          # full wizard: version → bootable media
python3 easy_hackintosh.py scan     # hardware scan only (→ build/hardware.json)
python3 easy_hackintosh.py efi      # regenerate the EFI only (kexts + config)
python3 easy_hackintosh.py image    # rebuild media from the existing EFI
```

Non-interactive selection: `EH_VERSION=sequoia python3 easy_hackintosh.py`.

### Output

Everything lands in `build/` (delete `build/` to start over):

| File | Content |
|---|---|
| `build/out/macOS-<version>.iso` | Hybrid bootable ISO, single file (Linux — USB or QEMU) |
| `build/EFI/` | Generated OpenCore EFI folder |
| `build/out/run-qemu.sh` | Boots the ISO in a VM (Linux) |
| `build/hardware.json` | Hardware scan results |

**Test in a VM (Linux):** `build/out/run-qemu.sh`

**Write to USB (Linux)** — ⚠️ wipes the stick, double-check `/dev/sdX`:

```bash
sudo dd if=build/out/macOS-*.iso of=/dev/sdX bs=4M oflag=sync status=progress
```

**Windows**: the script detects USB sticks, asks for confirmation (`OUI`), then
formats GPT/FAT32 and copies the EFI + recovery via `diskpart`.

## ⚠️ Good to know (honesty)

- **Online "recovery" installer**: macOS is downloaded during installation
  (internet required). A full offline installer needs `createinstallmedia`,
  which only exists on macOS.
- **Automated at build time**: universal *boot-safe* ACPI SSDTs
  ([Dortania](https://github.com/dortania/Getting-Started-With-ACPI): EC, USBX, AWAC,
  plugin-type, PNLF), **USB** via `SSDT-RHUB` (re-enumerates all ports), and **Wi-Fi**
  (Intel `AirportItlwm` picked per version, or Broadcom `AirportBrcmFixup`).
- The EFI is still a **starting point**, not a perfect turnkey config. No tool guarantees
  a first-try boot. Optional/advanced tuning:
  - **Precise USB mapping** (15-port-per-controller limit) → USBToolBox on Windows;
  - **Intel Wi-Fi on Sequoia/Tahoe**: no stable build yet → Sonoma build as fallback, verify;
  - very specific ACPI → SSDTTime + [Dortania guide](https://dortania.github.io/OpenCore-Install-Guide/).
- **Tahoe (26)**: the last macOS version with any Intel support, but **only 4 real models**
  (MacPro7,1, MacBookPro16,1/16,2, iMac20,1/20,2) — the macOS installer rejects the spoofed
  SMBIOS if it doesn't match one of these. macOS 27 will be Apple Silicon only.
- **Laptops** are trickier (battery, sleep, Wi-Fi, USB).

## Auto-handled hardware

| Component | Detection → kext / SSDT |
|---|---|
| Intel iGPU / AMD dGPU | WhateverGreen |
| Audio (Realtek ALC…) | AppleALC + starting `layout-id` |
| Intel / Realtek Ethernet | IntelMausi / RealtekRTL8111 / LucyRTL8125 |
| Intel / Broadcom Wi-Fi | AirportItlwm (per version) / AirportBrcmFixup |
| USB | SSDT-RHUB (port re-enumeration) |
| ACPI (EC, clock, CPU, backlight) | SSDT-EC/USBX, SSDT-AWAC, SSDT-PLUG, SSDT-PNLF |
| NVMe | NVMeFix |
| SMC (required) | VirtualSMC + plugins |

## Credits

Built on [OpenCorePkg](https://github.com/acidanthera/OpenCorePkg),
[Acidanthera](https://github.com/acidanthera) kexts and the
[Dortania guide](https://dortania.github.io/OpenCore-Install-Guide/).
No macOS binaries are redistributed.
