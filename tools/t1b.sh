#!/usr/bin/env bash
# t1b.sh — bring up the full T1 chain on one laptop and watch it:
#   PX4 SIH (VM) -> shuttle -> board 3 (held in reset) -> board 1 UART -> 2.4 GHz -> wlp0s20f3 -> relay -> QGC:14560
# Rule: board 3 is the ONLY ESP32 plugged into this laptop. Board 1 runs from a charger / power bank.
# Usage: tools/t1b.sh            (Ctrl-C stops shuttle + relay; PX4 keeps running in the VM)
set -euo pipefail
cd "$(dirname "$0")/.."
UV=~/.local/bin/uv
LOG=logs/t1b-$(date +%Y%m%d-%H%M%S); mkdir -p "$LOG"

# 1. exactly one CP2102 on this laptop (by-path has usb + usbv2 aliases for the same tty -> dedupe)
mapfile -t TTYS < <(for l in /dev/serial/by-path/*port0; do readlink -f "$l"; done 2>/dev/null | sort -u)
[ "${#TTYS[@]}" -eq 1 ] || { echo "FAIL: expected exactly 1 USB serial device (board 3), found ${#TTYS[@]}: ${TTYS[*]:-none}"; exit 1; }
DEV=$(ls /dev/serial/by-path/*port0 | head -1)
echo "adapter: $DEV -> ${TTYS[0]}"

# 2. on the board's AP, default route NOT via the ESP32
ip -4 -br addr show wlp0s20f3 | grep -q "192\.168\.2\." || { echo "FAIL: wlp0s20f3 not on the DroneBridge AP (nmcli con up tether-ap)"; exit 1; }
ip route | grep -q "^default.*wlp0s20f3" && echo "WARN: default route via the ESP32 — set ipv4.never-default yes"

# 3. PX4 SIH up in the VM, TETHER instance -> host :14601
LIBVIRT_DEFAULT_URI=qemu:///session virsh domstate dronelab | grep -q running || {
  LIBVIRT_DEFAULT_URI=qemu:///session virsh start dronelab; echo "waiting for VM ssh"; for _ in $(seq 60); do tools/vmssh true 2>/dev/null && break; sleep 2; done; }
tools/vmssh 'bash -s' < tools/guest_px4_sih.sh | tail -1

# 4. shuttle + relay
$UV run python -u tools/shuttle_passthrough.py --dev "$DEV" --baud 115200 >"$LOG/shuttle.log" 2>&1 & SH=$!
$UV run python -u tools/relay_ground.py >"$LOG/relay.log" 2>&1 & RL=$!
trap 'kill $SH $RL 2>/dev/null; echo; echo "stopped. logs in $LOG"' EXIT INT TERM
sleep 3

# 5. watch: DroneBridge's own counters prove bytes crossed the UART and decoded as MAVLink
echo "t    | shuttle (PX4->serial)                     | relay (radio->QGC)          | board: uart bytes / mav msgs"
for i in $(seq 1 600); do
  st=$(curl -s -m 1 "http://$(nmcli -t -f DHCP4.OPTION dev show wlp0s20f3 | sed -n 's/.*dhcp_server_identifier = //p')/api/system/stats" \
       | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["read_bytes"], "/", d["serial_dec_mav_msgs"])' 2>/dev/null || echo "?")
  printf "%4ds | %-42s | %-27s | %s\n" "$i" "$(tail -1 "$LOG/shuttle.log" | cut -c1-42)" "$(tail -1 "$LOG/relay.log" | cut -c1-27)" "$st"
  sleep 1
done
