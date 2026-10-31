# TETHER — demo v2: the Fort Mason bay mission

Live, no slides, ~2:00. Rehearse ×3 from 21:15. Numbers in ⟨⟩ come from `notes/evidence/bay-*/TIMELINE.txt`.

## The set
- **Laptop 2 (ground station, teammate):** QGC on the left (Fly view, map of Fort Mason, offline tiles),
  `dash.py` on the right (giant PICTURE AGE, tier strip). This is the operator's screen — face it to the judges.
- **Laptop 1 (the aircraft):** PX4 SIH + `air.py --range-model`. Its only link to laptop 2 is board 1.
- **Board 1** (ESP32, DroneBridge AP) on its power bank between the laptops; the metal tin / foil next to it.
- Cards on the table: disclosure (below) and the one-line result.
- Fallback if the two-laptop split isn't up: single laptop `tools/demo.sh bay-rf` (radio via board 1 → board 3),
  then `tools/demo.sh bay` (emulated, red EMULATED banner). Same story, same commands.

## Run sheet (start the mission ~20 s before the judges arrive: `mission_bay.py --go --watch`)
| t | On screen | Line |
|---|---|---|
| 0:00 | Drone climbing out of Fort Mason on the QGC map; picture age 0.0x s | "This drone just took off from this building. Its radio is that $7 ESP32. The only link between these two laptops is through it — close the tin and they're cut off." |
| 0:20 | (optional) judge closes the tin → BLACKOUT on the dash → open → recovers | "That's real 2.4 GHz." |
| 0:35 | ~250 m: dash tier strip drops T1/T2, QGC banner **"TETHER: link degraded"** | "Out over the water the radio loses capacity — modelled from range, disclosed. TETHER measures how stale the operator's picture is and tells PX4, in MAVLink's own command, to stop sending bulk. Picture stays fresh." |
| 1:00 | ~560 m: picture age climbs red; ~3 s later QGC **"TETHER: picture lost over water - RTL"**, PX4 "Returning to launch"; turns at 634 m (RTL fired at 587 m) | "Now even the critical set doesn't fit. PX4's own failsafe never fires — it watches whether *its commands* arrive, and they do. The operator is flying blind anyway. TETHER watches what the operator actually *sees* — and brings it home while commands still get through." |
| 1:30 | Terminal: `copilot.py explain` → 3–5 line incident report | "Claude writes the incident report from the logs. It never flies the drone — the model proposes, the loop enforces." |
| 1:45 | Card / timeline: TETHER off | "Same mission, TETHER off: into the blackout at 804 m, the operator blind for 104 s (picture up to 50 s old), drifted to 995 m before a blind manual RTL. With TETHER: turned home at 634 m and the picture never went dark. We don't create bandwidth. We decide who gets it — and when to come home." |

**If asked "is the radio real?"** — yes: PX4's telemetry crosses the ESP32 at 2.4 GHz; the tin proves it. The
range→capacity curve is synthetic (we can't fly 600 m over the Bay indoors) and it's labelled.
**"Isn't this just PX4's datalink failsafe?"** — PX4's `NAV_DLL_ACT` triggers on lost GCS heartbeats
(the uplink). In an asymmetric link the uplink survives while the downlink dies; PX4 never sees it.
**"Why not just lower the rates?"** — a static rate is wrong in both directions when capacity moves; shown in `PREREG.md` / `logs/sweep-*`.

## Disclosure card (print / write it)
> **Before 17:00 (prep):** PX4 SIH environment, DroneBridge flash + config (prebuilt, not ours), bring-up probes
> (rate command, traffic census), interface contract, pre-registered predictions.
> **17:00–22:00 (sprint):** air.py (link emulator: queue, capacity squeeze, range model), ground.py (picture-age
> measurement, tiered shedding via MAV_CMD_SET_MESSAGE_INTERVAL, downlink-aware RTL failsafe, STATUSTEXT to QGC),
> dash.py, copilot.py (Claude), mission_bay.py, sweep/analyze, every run shown.
> **Synthetic:** the capacity-vs-range curve and the squeeze. **Real:** PX4, the 2.4 GHz ESP32 hop, MAVLink commands.
> **Not ours:** PX4 (BSD-3), DroneBridge for ESP32 (Apache-2.0), QGroundControl, Claude API.
