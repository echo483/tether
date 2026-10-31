#!/usr/bin/env bash
# t1_diag.sh — ~40 s offline: join the TETHER AP, run tools/t1_diag.py, rejoin venue WiFi, print report path.
# Board 1 on the power bank, board 3 on the laptop (only USB serial device). Nothing else needs to run.
cd "$(dirname "$0")/.."
VENUE="${VENUE:-Founders Inc-Guest}"
OUT="logs/diag-$(date +%H%M%S).txt"; mkdir -p logs
pkill -f shuttle_passthrough 2>/dev/null; pkill -f relay_ground 2>/dev/null
{
  echo "== $(date) =="
  nmcli con up tether-ap >/dev/null 2>&1 || echo "WARN: could not join tether-ap"
  sleep 2; ip -4 -br addr show wlp0s20f3
  ~/.local/bin/uv run python tools/t1_diag.py
} 2>&1 | tee "$OUT"
nmcli con up "$VENUE" >/dev/null 2>&1 && echo "back on $VENUE" || echo "WARN: rejoin $VENUE manually"
echo "report: $OUT"
