#!/usr/bin/env bash
# preflight.sh — read-only go/no-go for the TETHER rig. Every line is PASS / FAIL / WARN.
# Run at the venue before 17:00, after any reboot, and at 21:45 before judging.
cd "$(dirname "$0")/.."
UV=~/.local/bin/uv; fails=0
ok()   { printf "PASS  %s\n" "$*"; }
bad()  { printf "FAIL  %s\n" "$*"; fails=$((fails+1)); }
warn() { printf "WARN  %s\n" "$*"; }

# power + disk
[ "$(cat /sys/class/power_supply/AC*/online 2>/dev/null | head -1)" = "1" ] && ok "laptop on AC power" || warn "laptop on battery"
[ "$(df --output=avail -BG ~ | tail -1 | tr -dc 0-9)" -gt 5 ] && ok "disk > 5G free" || bad "disk nearly full"

# serial: exactly one CP2102 (= board 3), ACL lets us open it
mapfile -t T < <(for l in /dev/serial/by-path/*port0; do readlink -f "$l"; done 2>/dev/null | sort -u)
[ "${#T[@]}" -eq 1 ] && ok "one USB serial device: ${T[0]}" || bad "expected 1 USB serial device (board 3 only), found ${#T[@]}"
[ "${#T[@]}" -ge 1 ] && { [ -r "${T[0]}" ] && [ -w "${T[0]}" ] && ok "tty is read/write for $USER" || bad "no rw on ${T[0]} (udev uaccess rule / dialout)"; }

# wifi on the DroneBridge AP, default route not through it
ip -4 -br addr show wlp0s20f3 | grep -q "192\.168\.2\." && ok "wlp0s20f3 on the TETHER AP" || bad "wlp0s20f3 not on the AP: nmcli con up tether-ap"
ip route | grep -q "^default.*wlp0s20f3" && warn "default route via the ESP32 (fine offline, breaks internet)" || ok "default route not via ESP32"
mullvad status 2>/dev/null | grep -q "^Connected" && warn "Mullvad connected" || ok "Mullvad not connected"

# board 1 config matches what the code assumes
$UV run python - <<'EOF' && ok "board 1 settings match (AP, MAVLink, 115200, tx19/rx18)" || bad "board 1 settings mismatch or unreachable (tools/db_set.py --read)"
import json, sys, urllib.request
sys.path.insert(0, "tools"); from tnet import DB_IP
d = json.load(urllib.request.urlopen(f"http://{DB_IP}/api/settings", timeout=4))
want = {"esp32_mode": 1, "proto": 4, "baud": 115200, "gpio_tx": 19, "gpio_rx": 18, "gpio_rts": 0, "gpio_cts": 0}
bad = {k: d.get(k) for k, v in want.items() if d.get(k) != v}
print("      ssid", d.get("ssid"), "chan", d.get("wifi_chan"), "mismatch:" if bad else "", bad or "")
sys.exit(1 if bad else 0)
EOF

# VM + PX4 stream
LIBVIRT_DEFAULT_URI=qemu:///session virsh domstate dronelab 2>/dev/null | grep -q running && ok "VM dronelab running" || bad "VM not running (t1b.sh starts it)"
tools/vmssh true 2>/dev/null && ok "VM ssh" || bad "VM ssh failed"
ss -ulpn 2>/dev/null | grep -q ":14601 " && warn "something already bound to 14601 (old shuttle?)" || {
  n=$(timeout 6 $UV run python tools/mavframes.py 14601 3 2>/dev/null | grep -c "ATTITUDE ")
  [ "$n" -ge 1 ] && ok "PX4 TETHER stream arriving on localhost:14601" || bad "no PX4 stream on 14601 (tools/vmssh 'bash -s' < tools/guest_px4_sih.sh)"; }

# ports: QGC must not own 14550 / the tty
ss -ulpn 2>/dev/null | grep -q "QGroundCo.*:14550 " && bad "QGC is bound to 14550 (autoconnect back on?)" || ok "14550 free of QGC"
$UV run python -c "import pymavlink, serial, numpy, matplotlib" 2>/dev/null && ok "python env imports" || bad "uv env broken"

echo; [ "$fails" -eq 0 ] && echo "GO" || echo "NO-GO: $fails failure(s)"
exit "$fails"
