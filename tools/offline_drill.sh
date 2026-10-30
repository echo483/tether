#!/usr/bin/env bash
# offline_drill.sh — prove the VM + PX4 cold-start with NO internet (the venue condition).
# Run with Ethernet unplugged (and not on any internet WiFi). Takes ~2 min. Prints PASS/FAIL.
set -u
cd "$(dirname "$0")/.."
V="env LIBVIRT_DEFAULT_URI=qemu:///session virsh"
ip route | grep -q '^default' && echo "WARN: a default route exists — unplug Ethernet first for a true drill"
$V domstate dronelab | grep -q running && { echo "shutting VM down…"; $V shutdown dronelab >/dev/null
  for _ in $(seq 40); do $V domstate dronelab | grep -q "shut off" && break; sleep 2; done
  $V domstate dronelab | grep -q "shut off" || $V destroy dronelab >/dev/null; }
echo "starting VM…"; $V start dronelab >/dev/null || { echo "FAIL: VM did not start (passt?)"; exit 1; }
for _ in $(seq 60); do tools/vmssh true 2>/dev/null && break; sleep 2; done
tools/vmssh true 2>/dev/null || { echo "FAIL: no ssh into the VM"; exit 1; }
echo "guest network: $(tools/vmssh "ip -4 -br addr show | grep -v '^lo'; ip route | head -1" | tr '\n' ' ')"
tools/vmssh 'bash -s' < tools/guest_px4_sih.sh | tail -1
sleep 3
n=$(timeout 8 ~/.local/bin/uv run python tools/mavframes.py 14601 4 2>/dev/null | grep -c "ATTITUDE ")
[ "$n" -ge 1 ] && echo "PASS: offline cold start — PX4 stream on localhost:14601" || { echo "FAIL: no PX4 stream on 14601"; exit 1; }
