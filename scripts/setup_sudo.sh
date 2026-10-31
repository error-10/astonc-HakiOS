#!/usr/bin/env bash
# One-time: enable passwordless sudo for the WSL user (password passed via $SUDO_PASS env).
set -uo pipefail
: "${SUDO_PASS:?SUDO_PASS not set}"
U=$(id -un)
echo "$SUDO_PASS" | sudo -S -p '' bash -c "echo '$U ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/dsh-nopasswd && chmod 440 /etc/sudoers.d/dsh-nopasswd" 2>&1
if sudo -n true 2>/dev/null; then echo "SUDO OK for $U"; else echo "SUDO SETUP FAILED"; exit 1; fi
