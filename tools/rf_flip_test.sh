#!/usr/bin/env bash
# rf_flip_test.sh — ~30 s offline: prove PX4 telemetry crosses REAL 2.4 GHz in the working direction:
#   PX4 -> air.py --radio-host board1 (laptop WiFi) ~~RF~~ board 1 -> UART TX (D19) -> board 3 -> laptop serial
# Joins the TETHER AP, runs the test, rejoins venue WiFi, prints PASS/FAIL. Board 3 = only USB serial device.
cd "$(dirname "$0")/.."
VENUE="${VENUE:-Founders Inc-Guest}"
OUT="logs/rfflip-$(date +%H%M%S).txt"; mkdir -p logs
pkill -f "tools/air.py" 2>/dev/null; pkill -f shuttle_passthrough 2>/dev/null; sleep 0.5
{
  nmcli con up tether-ap >/dev/null 2>&1 || echo "WARN: could not join tether-ap"
  sleep 2; ip -4 -br addr show wlp0s20f3
  ~/.local/bin/uv run python -u tools/air.py --radio-host 192.168.2.1 --log logs/rfflip-air.jsonl > logs/rfflip-air.out 2>&1 &
  AIR=$!; sleep 2
  ~/.local/bin/uv run python - <<'EOF'
import glob, time, collections
import serial
from pymavlink.dialects.v20 import common as mav
dev = sorted(set(glob.glob("/dev/serial/by-path/*port0")))[0]
s = serial.Serial(); s.port, s.baudrate, s.timeout = dev, 115200, 0.05
s.dtr, s.rts = False, True; s.open(); s.rts = False; time.sleep(0.1); s.rts = True; time.sleep(0.4); s.reset_input_buffer()
p = mav.MAVLink(None); p.robust_parsing = True
c = collections.Counter(); nb = 0; t0 = time.time(); off = None; ages = []
while time.time() - t0 < 12:
    b = s.read(4096); nb += len(b)
    for m in p.parse_buffer(b) or []:
        c[(m.get_type(), m.get_srcComponent())] += 1
        if m.get_type() == "ATTITUDE" and m.get_srcComponent() == 1:
            x = time.time() - m.time_boot_ms / 1000; off = x if off is None else min(off, x); ages.append(x - off)
s.close()
att = c[("ATTITUDE", 1)]
print(f"serial: {nb} B in 12 s = {nb/12:.0f} B/s; PX4 ATTITUDE {att} ({att/12:.1f} Hz); top {c.most_common(6)}")
if ages: print(f"ATTITUDE queueing delay above min: median {sorted(ages)[len(ages)//2]*1000:.0f} ms")
print("PASS: PX4 telemetry over real RF (laptop WiFi -> board 1 -> UART -> board 3)" if att > 50 else "FAIL: no PX4 ATTITUDE over the RF path")
EOF
  kill $AIR 2>/dev/null; sleep 0.5; tail -2 logs/rfflip-air.out
} 2>&1 | tee "$OUT"
nmcli con up "$VENUE" >/dev/null 2>&1 && echo "back on $VENUE" || echo "WARN: rejoin $VENUE manually"
echo "report: $OUT"
