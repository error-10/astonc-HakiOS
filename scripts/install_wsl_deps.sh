#!/usr/bin/env bash
# Install build dependencies for the HakiOS / Mu-Silicium / XNU toolchain inside WSL Ubuntu.
# Requires passwordless sudo (set up by setup_sudo.sh) or to be run as root.
set -uo pipefail
WS=/mnt/c/Users/96943/Desktop/ios
LOG=$WS/logs/apt.log
mkdir -p "$WS/logs"
exec > >(tee -a "$LOG") 2>&1
echo "==== $(date -Is) apt install start ===="

PKGS=(
  build-essential
  git curl wget
  tar xz-utils zip unzip
  make flex bison m4 perl
  python3 python3-pip python3-venv python3-dev python3-git
  autoconf automake libtool pkg-config
  clang lld llvm
  nasm
  uuid-dev libssl-dev
  gcc-aarch64-linux-gnu
  binutils-aarch64-linux-gnu
  gettext locales gnupg ca-certificates
  mtools dosfstools
  lz4 zstd
  libncurses-dev libelf-dev
  patch diffutils
  cmake ninja-build
  rsync
)

echo "--- apt-get update"
sudo -n true 2>/dev/null || { echo "NO PASSWORDLESS SUDO"; exit 11; }
sudo apt-get update -y || echo "APT UPDATE FAILED"
echo "--- apt-get install"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${PKGS[@]}" || echo "APT INSTALL PARTIAL/Failed"

echo "--- versions"
for c in cc clang clang++ ld.lld llvm-ar llvm-objcopy nasm aarch64-linux-gnu-gcc python3 pip3 dtc mcopy rsync lz4 cmake ninja 7z 7za; do
  p=$(command -v "$c" 2>/dev/null)
  if [ -n "$p" ]; then printf '%-26s %s\n' "$c" "$p"; else printf '%-26s MISSING\n' "$c"; fi
done
clang --version 2>/dev/null | head -2
echo "==== $(date -Is) apt install done ===="
echo "READY_APT"
