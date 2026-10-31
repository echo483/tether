# TETHER

**Keeps a drone operator's picture fresh on a $7 radio.** TETHER measures how stale the telemetry
on the ground station really is, and when the link can't keep up it tells PX4 — with MAVLink's own
`SET_MESSAGE_INTERVAL` command — what to stop sending. Claude turns operator intent into the
priority policy; a deterministic loop enforces it.

Built at Night Hack (Founders, Inc., Oct 30 2026). Tag `sprint-start` marks the prep/sprint boundary;
see `DEMO.md` for the disclosure card (what was built before vs during the sprint).

## The rig
```
laptop 1 (air)                                                   laptop 2 (ground)
PX4 SIH ─UDP→ shuttle ─USB→ board 3 ─UART→ board 1 (DroneBridge AP) ~~2.4 GHz~~ WiFi → QGroundControl
```
Real PX4 autopilot (simulated quad), real ESP32 radio running DroneBridge for ESP32 (not ours),
real air gap — cover board 1 with a metal tin and the link dies.

## Teammate quickstart (ground station, laptop 2)
1. Join WiFi **`TETHER-nighthack`** (password from the team chat).
2. Open **QGroundControl** → Application Settings → Comm Links / AutoConnect: **UDP** checked.
3. That's it: when laptop 1 runs `tools/air_up.sh`, the drone appears in QGC within ~5 s.
   No vehicle? Open `http://192.168.2.1` in a browser — if the DroneBridge page loads, the WiFi part works.

## Docs
| File | What |
|---|---|
| `SCOPE.md` | what we build tonight, tiers and cut lines |
| `CONTRACT.md` | port map, log format, policy file — the interface between the two of us |
| `DEMO.md` | 2-minute run sheet, pitch lines, disclosure card |
| `PREREG.md` | predictions committed before the sprint |
| `RUNBOOK.md` · `PHYSICAL.md` | cold start, recovery, wiring check |
| `notes/` | evidence: PX4 probe, traffic census, DroneBridge facts, QGC config |

Credits: PX4 (BSD-3), DroneBridge for ESP32 (Apache-2.0), QGroundControl, Claude API.
