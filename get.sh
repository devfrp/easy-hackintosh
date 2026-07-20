#!/usr/bin/env sh
# get.sh — Linux : installe les dépendances, récupère easy-hackintosh, lance l'assistant.
# Usage :  curl -fsSL https://raw.githubusercontent.com/devfrp/easy-hackintosh/main/get.sh | sh
#   Variables : REPO=<url git>, DIR=<dossier cible>, EH_VERSION=<clé macOS>
set -eu

REPO="${REPO:-https://github.com/devfrp/easy-hackintosh}"
DIR="${DIR:-$HOME/easy-hackintosh}"
say() { printf '\033[36m::\033[0m %s\n' "$1"; }

if command -v pacman >/dev/null 2>&1; then
  say "Arch — installation des paquets"
  sudo pacman -S --needed --noconfirm python git curl unzip dosfstools gptfdisk mtools \
    pciutils usbutils qemu-full edk2-ovmf
elif command -v apt-get >/dev/null 2>&1; then
  say "Debian/Ubuntu — installation des paquets"
  sudo apt-get update
  sudo apt-get install -y python3 git curl unzip dosfstools gdisk mtools \
    pciutils usbutils qemu-system-x86 ovmf
elif command -v dnf >/dev/null 2>&1; then
  say "Fedora — installation des paquets"
  sudo dnf install -y python3 git curl unzip dosfstools gdisk mtools \
    pciutils usbutils qemu-system-x86 edk2-ovmf
else
  say "Distro non reconnue — installe : python git mtools gptfdisk pciutils usbutils qemu ovmf"
fi

if [ -d "$DIR/.git" ]; then
  say "Mise à jour de $DIR"; git -C "$DIR" pull --ff-only
else
  say "Clonage dans $DIR"; git clone --depth 1 "$REPO" "$DIR"
fi

say "Lancement de l'assistant"
cd "$DIR"
if [ -t 0 ]; then
  exec python3 easy_hackintosh.py
elif [ -r /dev/tty ]; then
  # stdin est le tube de `curl | sh` (déjà à EOF) : on rattache le terminal réel
  # pour que les prompts interactifs (choix de version, confirmation USB…) marchent.
  exec python3 easy_hackintosh.py < /dev/tty
else
  exec python3 easy_hackintosh.py
fi
