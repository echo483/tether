#!/usr/bin/env bash
# air_up.sh — the AIR side only (laptop 1). Laptop 1 stays on venue WiFi; it never joins the board's AP.
#   PX4 SIH (VM) -> shuttle -> board 3 (held in reset) -> board 1 UART -> 2.4 GHz -> laptop 2 (QGC)
# Rule: board 3 is the ONLY ESP32 on this laptop; board 1 runs from a power bank.
# Usage: tools/air_up.sh      (Ctrl-C stops the shuttle; PX4 keeps running in the VM)
set -euo pipefail
cd "$(dirname "$0")/.."
mapfile -t TTYS < <(for l in /dev/serial/by-path/*port0; do readlink -f "$l"; done 2>/dev/null | sort -u)
[ "${#TTYS[@]}" -eq 1 ] || { echo "FAIL: expected exactly 1 USB serial device (board 3), found ${#TTYS[@]}"; exit 1; }
DEV=$(ls /dev/serial/by-path/*port0 | head -1)
pkill -f shuttle_passthrough 2>/dev/null || true
LIBVIRT_DEFAULT_URI=qemu:///session virsh domstate dronelab | grep -q running || {
  LIBVIRT_DEFAULT_URI=qemu:///session virsh start dronelab
  echo "waiting for VM ssh"; for _ in $(seq 60); do tools/vmssh true 2>/dev/null && break; sleep 2; done; }
tools/vmssh 'bash -s' < tools/guest_px4_sih.sh | tail -1
echo "adapter: $DEV — shuttle running; laptop 2 should now see the vehicle in QGC"
exec ~/.local/bin/uv run python -u tools/shuttle_passthrough.py --dev "$DEV" --baud 115200
