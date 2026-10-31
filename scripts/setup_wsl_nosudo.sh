#!/usr/bin/env bash
# No-sudo bootstrap for the OnePlus Ace 3 (astonc / SM8550) HakiOS port build tree.
# Clones upstream sources + theos toolchain into $HOME/hackios, logs to the Windows workspace.
set -uo pipefail

WS=/mnt/c/Users/96943/Desktop/ios
LOG=$WS/logs/setup.log
mkdir -p "$WS/logs" "$WS/out"
exec > >(tee -a "$LOG") 2>&1
echo "==== $(date -Is) bootstrap start (no sudo) ===="
H=$HOME
mkdir -p "$H/hackios"
cd "$H/hackios" || exit 1
git config --global advice.detachedHead false
git config --global core.compression 9

step() { echo; echo "---- $(date -Is) $* ----"; }

# ---------------------------------------------------------------- 1. HakiOS upstream
step "clone hackios-xnu-kernel"
if [ ! -d hackios-os/.git ]; then
  git clone --depth 1 https://github.com/oosexgang/hackios-xnu-kernel.git hackios-os || echo "CLONE FAIL hackios-os"
else
  echo "hackios-os already present"
fi

# ---------------------------------------------------------------- 2. theos
step "theos"
if [ ! -d "$H/theos/.git" ]; then
  git clone https://github.com/theos/theos.git "$H/theos" || echo "CLONE FAIL theos"
fi
mkdir -p "$H/theos/toolchain/linux/iphone"
if [ ! -x "$H/theos/toolchain/linux/iphone/bin/clang" ]; then
  step "theos iOS toolchain"
  curl -fL --retry 3 -o /tmp/iOSToolchain.tar.xz \
    https://github.com/L1ghtmann/llvm-project/releases/latest/download/iOSToolchain-x86_64.tar.xz \
    && tar -xJf /tmp/iOSToolchain.tar.xz -C "$H/theos/toolchain/linux/iphone" --strip-components=2 \
    && rm -f /tmp/iOSToolchain.tar.xz || echo "TOOLCHAIN FAIL"
fi
mkdir -p "$H/theos/sdks"
if [ ! -d "$H/theos/sdks/iPhoneOS16.5.sdk" ]; then
  step "theos iPhoneOS16.5.sdk (sparse)"
  rm -rf /tmp/sdks
  git clone --depth 1 --filter=blob:none --sparse https://github.com/theos/sdks.git /tmp/sdks \
    && ( cd /tmp/sdks && git sparse-checkout set iPhoneOS16.5.sdk ) \
    && mv /tmp/sdks/iPhoneOS16.5.sdk "$H/theos/sdks/" || echo "SDK FAIL"
  rm -rf /tmp/sdks
fi

# ---------------------------------------------------------------- 3. Mu-Silicium (UEFI for aston already upstream)
step "clone Mu-Silicium + submodules"
if [ ! -d Mu-Silicium/.git ]; then
  git clone --depth 1 --recurse-submodules --shallow-submodules \
    https://github.com/Project-Silicium/Mu-Silicium.git Mu-Silicium || echo "CLONE FAIL Mu-Silicium"
else
  echo "Mu-Silicium already present"
fi

# ---------------------------------------------------------------- 4. python bits (user level)
step "pip user installs"
python3 -m pip install --user --break-system-packages lzfse 2>&1 | tail -n 3
python3 -m venv --help >/dev/null 2>&1 && echo "venv module ok" || echo "venv module MISSING"

# ---------------------------------------------------------------- 5. sanity report
step "tree status"
for d in hackios-os theos Mu-Silicium; do
  if [ -d "$H/hackios/$d" ] || [ -d "$H/$d" ]; then
    du -sh "$H/hackios/$d" 2>/dev/null || du -sh "$H/$d" 2>/dev/null
  else
    echo "MISSING $d"
  fi
done
echo "clang: $(ls -l "$H/theos/toolchain/linux/iphone/bin/clang" 2>/dev/null | head -1)"
echo "sdk:   $(ls -d "$H/theos/sdks/"*.sdk 2>/dev/null | tr '\n' ' ')"
echo "aston dtb: $(ls -l "$H/hackios/Mu-Silicium/Resources/DTBs/aston.dtb" 2>/dev/null)"
echo "==== $(date -Is) bootstrap done ===="
echo "READY_NO_SUDO"
