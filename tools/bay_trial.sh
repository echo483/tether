#!/usr/bin/env bash
# bay_trial.sh on|off — one measured Fort Mason bay mission, emulated link, unattended; prints the timeline.
#   on : TETHER manager on (failsafe armed) -> expect shed, RTL, landing at home
#   off: manager off -> expect blackout past 800 m; after 15 s in blackout we send RTL by hand to recover
# Logs: logs/bay-<arm>-<HHMMSS>/{air,ground}.jsonl + mission.out (+ dash PNG for 'on'). Leaves only PX4 running.
set -u
cd "$(dirname "$0")/.."
PY=~/.local/bin/uv; ARM=${1:-on}; OUT="logs/bay-$ARM-$(date +%H%M%S)"; mkdir -p "$OUT"
pkill -f "tools/[a]ir.py"; pkill -f "tools/[g]round.py"; pkill -f "tools/[m]ission_bay.py"; sleep 0.5
$PY run python -u tools/air.py --emulated --range-model --log "$OUT/air.jsonl" > "$OUT/air.out" 2>&1 & A=$!
sleep 1
$PY run python -u tools/ground.py --failsafe --mirror localhost:14571 --log "$OUT/ground.jsonl" > "$OUT/ground.out" 2>&1 & G=$!
trap 'kill $A $G $W $S 2>/dev/null; wait 2>/dev/null' EXIT
W=; S=
sleep 4
[ "$ARM" = on ] && $PY run python tools/knob.py on
if [ "$ARM" = on ]; then           # dash snapshot ~6 s after the RTL fires (30 s trace = the lead-up)
  ( for _ in $(seq 400); do grep -q '"what": "failsafe"' "$OUT/ground.jsonl" 2>/dev/null && break; sleep 1; done
    $PY run python tools/dash.py --dir "$OUT" --snapshot "$OUT/dash-rtl.png" --secs 6 > "$OUT/dash.out" 2>&1 ) & S=$!
fi
$PY run python -u tools/mission_bay.py --go --watch --watch-s 480 > "$OUT/mission.out" 2>&1 & W=$!
RTL_SENT=0; BO=0
while kill -0 $W 2>/dev/null; do
  sleep 1
  last=$(tail -1 "$OUT/air.jsonl" 2>/dev/null)
  if echo "$last" | grep -q '"blackout": true'; then BO=$((BO+1)); else BO=0; fi
  if [ $BO -ge 15 ] && [ $RTL_SENT = 0 ]; then
    echo "$(date +%T) 15 s in blackout: manual RTL (the operator's only option, blind)" | tee -a "$OUT/mission.out"
    echo "{\"t\": $(date +%s.%N), \"kind\": \"event\", \"what\": \"manual_rtl\"}" >> "$OUT/manual.jsonl"
    $PY run python tools/mission_bay.py --rtl >> "$OUT/mission.out" 2>&1; RTL_SENT=1
  fi
done
sleep 2
$PY run python tools/bay_timeline.py "$OUT" | tee "$OUT/TIMELINE.txt"
echo "logs: $OUT"
