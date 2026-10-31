#!/usr/bin/env bash
# demo.sh — one command per demo mode. Starts air.py + ground.py (+ dash), Ctrl-C stops everything.
#   tools/demo.sh emulated      # whole loop on this laptop, no radio (stays online)
#   tools/demo.sh rf            # REAL 2.4 GHz: laptop WiFi -> board 1 -> UART -> board 3 (laptop goes on the TETHER AP)
#   tools/demo.sh sweep-rf [N]  # N paired runs (default 10) over the real radio, then the results table
#   tools/demo.sh sweep-emu [N] # same, emulated
#   tools/demo.sh bay           # Fort Mason bay mission: emulated link, capacity falls with range, TETHER failsafe armed
#   tools/demo.sh bay-rf        # same story over the REAL radio (laptop goes on the TETHER AP)
# Then: QGC (~/.local/opt/qgc/squashfs-root/AppRun) and the hot keys: uv run python tools/knob.py
# TETHER starts OFF in live modes; `knob.py on` turns it on (that is the demo beat).
set -u
cd "$(dirname "$0")/.."
PY=~/.local/bin/uv; MODE=${1:-emulated}; N=${2:-10}
VENUE="${VENUE:-Founders Inc-Guest}"
B1=$(python3 -c "print('.'.join(map(str,(192,168,2,1))))")
DEV=$(ls /dev/serial/by-path/*port0 2>/dev/null | head -1)
pkill -f "tools/[a]ir.py" 2>/dev/null; pkill -f "tools/[g]round.py" 2>/dev/null; pkill -f "tools/[d]ash.py" 2>/dev/null
pkill -f "tools/[m]ission_bay.py" 2>/dev/null; sleep 0.5
tools/vmssh true 2>/dev/null || { echo "VM not reachable — starting"; LIBVIRT_DEFAULT_URI=qemu:///session virsh start dronelab; sleep 30; }
timeout 6 $PY run python tools/mavframes.py 14601 2 2>/dev/null | grep -q "ATTITUDE " || tools/vmssh 'bash -s' < tools/guest_px4_sih.sh | tail -1

rf_on()  { nmcli con up tether-ap >/dev/null && echo "WiFi -> TETHER AP (offline from the internet now)"; }
rf_off() { nmcli con up "$VENUE" >/dev/null && echo "WiFi -> $VENUE"; }
need_dev() { [ -n "$DEV" ] || { echo "FAIL: board 3 not plugged in"; exit 1; }; }

case "$MODE" in
  emulated|rf)
    if [ "$MODE" = rf ]; then need_dev; rf_on; AIR="--radio-host $B1"; GND="--serial $DEV"; else AIR="--emulated"; GND=""; fi
    $PY run python -u tools/air.py $AIR > logs/live-air.out 2>&1 & A=$!
    sleep 1
    $PY run python -u tools/ground.py $GND > logs/live-ground.out 2>&1 & G=$!
    sleep 2
    $PY run python tools/dash.py > logs/live-dash.out 2>&1 & D=$!
    trap 'kill $A $G $D 2>/dev/null; [ "$MODE" = rf ] && rf_off; echo stopped' EXIT INT TERM
    echo "running ($MODE). QGC: ~/.local/opt/qgc/squashfs-root/AppRun   keys: uv run python tools/knob.py"
    tail -f logs/live-ground.out
    ;;
  bay|bay-rf)
    if [ "$MODE" = bay-rf ]; then need_dev; rf_on; AIR="--radio-host $B1"; GND="--serial $DEV"; else AIR="--emulated"; GND=""; fi
    $PY run python -u tools/air.py $AIR --range-model > logs/live-air.out 2>&1 & A=$!
    sleep 1
    $PY run python -u tools/ground.py $GND --failsafe --mirror localhost:14571 > logs/live-ground.out 2>&1 & G=$!
    sleep 2
    $PY run python tools/dash.py > logs/live-dash.out 2>&1 & D=$!
    trap 'kill $A $G $D 2>/dev/null; [ "$MODE" = bay-rf ] && rf_off; echo stopped' EXIT INT TERM
    cat <<EOF
running ($MODE). Capacity follows range from home (Fort Mason): <250 m unlimited, <550 m 1600 B/s, <800 m 700 B/s,
beyond = BLACKOUT (air.py --range-model; synthetic, disclosed). TETHER manager starts OFF; its RTL failsafe is armed.
QGC: ~/.local/opt/qgc/squashfs-root/AppRun      keys: $PY run python tools/knob.py
 A) WITHOUT TETHER (drone is lost):   $PY run python tools/mission_bay.py --go --watch
      -> flies north over the bay, blackout past 800 m, holds at 1100 m; nothing brings it back.
      recover:  $PY run python tools/mission_bay.py --rtl      (wait for it to land + auto-disarm)
 B) WITH TETHER (drone comes home):   $PY run python tools/knob.py on
                                      $PY run python tools/mission_bay.py --go --watch
      -> sheds bulk at ~260 m, picture lost past 550 m, TETHER commands RTL ~3 s later, lands at Fort Mason.
      re-arm the failsafe for another run: $PY run python tools/knob.py fsreset
EOF
    tail -f logs/live-ground.out
    ;;
  sweep-rf|sweep-emu)
    if [ "$MODE" = sweep-rf ]; then need_dev; rf_on; AIR="--radio-host $B1"; GND=" --serial $DEV"; else AIR="--emulated"; GND=""; fi
    trap '[ "$MODE" = sweep-rf ] && rf_off' EXIT INT TERM
    OUTD="logs/sweep-$(date +%H%M)"
    $PY run python tools/sweep.py --launch --pairs "$N" --c-lo 1600 --boundary-c 700 --logs "$OUTD" \
      --air-cmd "{py} {air_py} --log {dir}/air.jsonl --seed {seed} $AIR" \
      --ground-cmd "{py} {ground_py} --log {dir}/ground.jsonl$GND{manager_flag}"
    $PY run python tools/analyze.py "$OUTD" | tee "$OUTD/RESULTS.txt"
    ;;
  *) sed -n 2,11p "$0";;
esac
