#!/usr/bin/env bash
# Start PX4 SIH (sihsim_quadx) headless in tmux session "px4" inside the dronelab guest, then add
# the TETHER mavlink instance aimed at the passt gateway (= host loopback under passt).
# Run from the host:   tools/vmssh 'bash -s' < tools/guest_px4_sih.sh
# Idempotent: if px4 already runs and the instance's UDP port is bound, it only reports.
set -euo pipefail
B=$HOME/PX4-Autopilot/build/px4_sitl_default
TETHER_LOCAL=${TETHER_LOCAL:-14556}   # PX4 binds this UDP port in the guest
TETHER_REMOTE=${TETHER_REMOTE:-14601} # PX4 sends to <gateway>:this -> host loopback (localhost):this
GW=$(ip route | awk '/default/{print $3; exit}')   # changes per network: never hardcode
[ -n "$GW" ] || { echo "no default route in guest"; exit 1; }
if ! pgrep -f "[b]in/px4 -i 0" >/dev/null; then
  tmux kill-session -t px4 2>/dev/null || true
  tmux new-session -d -s px4 -x 200 -y 50 \
    "cd $B/rootfs && PX4_SIM_MODEL=sihsim_quadx ../bin/px4 -i 0 2>&1 | tee /tmp/px4-sih.log"
  for _ in $(seq 60); do grep -q "Startup script returned" /tmp/px4-sih.log 2>/dev/null && break; sleep 0.5; done
fi
cd "$B/rootfs"
# px4-mavlink client output goes to the PX4 console, so detect the instance by its bound UDP port
if ! ss -uln | grep -q ":$TETHER_LOCAL "; then
  # no -m => mode Normal (PX4 rejects "-m normal" with "invalid mode"); -r high so PX4 does not scale streams
  ../bin/px4-mavlink start -u "$TETHER_LOCAL" -o "$TETHER_REMOTE" -t "$GW" -r 400000
  sleep 1
fi
tmux capture-pane -p -t px4 -S -2000 | grep -E "Ready for takeoff|udp port $TETHER_LOCAL" | tail -2 || true
ss -uln | grep -q ":$TETHER_LOCAL " || { echo "TETHER instance NOT bound"; exit 1; }
echo "PX4 SIH up; TETHER instance udp $TETHER_LOCAL -> gateway:$TETHER_REMOTE (gateway computed in guest)"
