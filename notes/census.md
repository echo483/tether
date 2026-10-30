# census.md — PX4 SIH offered load on the TETHER instance (Phase D)

- **Date:** 2026-10-30 12:41:52–12:42:52 PDT (60 s window).
- **Source:** PX4 v1.16.2 SITL, SIH `sihsim_quadx`, in VM `dronelab`; vehicle disarmed on the ground.
- **Instance measured:** a Normal-mode mavlink instance started exactly like the shuttle's
  (`mavlink start -u 14557 -o 14561 -t <guest gateway> -r 400000`, no `-m` => Normal, no FTP, no `-s`).
  It is a config clone of the shuttle instance (#5, udp 14556 -> host 14560). I used the clone because
  QGroundControl (pid 28531, not started by me) was bound to host UDP 14560 at the time and attached to #5;
  the clone had no GCS attached, so this is pure PX4-offered load. `-r 400000` B/s is >> L, so PX4's
  rate multiplier stayed 1.000 (no scaling): these are the Normal-mode default stream rates.
- **Instrument:** `tools/census.py --port 14561 --secs 60` (host, uv venv, receive-only socket bound to
  localhost). Each UDP datagram split into MAVLink frames by length byte (`tools/mavframes.py`);
  bytes = full wire length per packet (MAVLink v2: 10 B header + payload + 2 B CRC; signed packets would
  add 13 B — **0 signed packets seen**). Names via pymavlink 2.4.50 common dialect (+4 development-dialect
  ids named by hand). Clock = host `time.monotonic()`. Raw: `notes/evidence/census-14561.{md,json}`.
- **n:** 60 s window, 3340 datagrams = 3340 packets (exactly 1 MAVLink packet per datagram; 55.7/s,
  mean 41.3 B) across 27 msgids. Sum of frame bytes == UDP payload bytes (2300.4 B/s), so no
  unparsed bytes.

## Table (sorted by bytes/s)

| # | msgid | name | n (60 s) | Hz | bytes/s | mean pkt B | crit |
|---|---|---|---|---|---|---|---|
| 1 | 30 | ATTITUDE | 882 | 14.70 | 588.0 | 40.0 | Y |
| 2 | 31 | ATTITUDE_QUATERNION | 589 | 9.82 | 431.9 | 44.0 | Y |
| 3 | 24 | GPS_RAW_INT | 294 | 4.90 | 274.4 | 56.0 |  |
| 4 | 33 | GLOBAL_POSITION_INT | 294 | 4.90 | 191.1 | 39.0 | Y |
| 5 | 74 | VFR_HUD | 235 | 3.92 | 113.6 | 29.0 |  |
| 6 | 83 | ATTITUDE_TARGET | 117 | 1.95 | 93.6 | 48.0 |  |
| 7 | 85 | POSITION_TARGET_LOCAL_NED | 88 | 1.47 | 92.4 | 63.0 |  |
| 8 | 12901 | OPEN_DRONE_ID_LOCATION | 58 | 0.97 | 67.7 | 70.0 |  |
| 9 | 1 | SYS_STATUS | 58 | 0.97 | 50.3 | 52.0 | Y |
| 10 | 36 | SERVO_OUTPUT_RAW | 58 | 0.97 | 47.4 | 49.0 |  |
| 11 | 141 | ALTITUDE | 58 | 0.97 | 42.5 | 44.0 |  |
| 12 | 32 | LOCAL_POSITION_NED | 58 | 0.97 | 38.7 | 40.0 | Y |
| 13 | 12904 | OPEN_DRONE_ID_SYSTEM | 58 | 0.97 | 35.8 | 37.0 |  |
| 14 | 242 | HOME_POSITION | 29 | 0.48 | 32.4 | 67.0 |  |
| 15 | 8 | LINK_NODE_STATUS | 58 | 0.97 | 28.9 | 29.9 |  |
| 16 | 230 | ESTIMATOR_STATUS | 29 | 0.48 | 26.1 | 54.0 |  |
| 17 | 147 | BATTERY_STATUS | 29 | 0.48 | 25.6 | 53.0 | Y |
| 18 | 29 | SCALED_PRESSURE | 58 | 0.97 | 25.1 | 26.0 |  |
| 19 | 0 | HEARTBEAT | 58 | 0.97 | 20.3 | 21.0 | Y |
| 20 | 42 | MISSION_CURRENT | 58 | 0.97 | 15.5 | 16.0 |  |
| 21 | 380 | TIME_ESTIMATE_TO_TARGET | 29 | 0.48 | 15.5 | 32.0 |  |
| 22 | 245 | EXTENDED_SYS_STATE | 58 | 0.97 | 13.5 | 14.0 | Y |
| 23 | 132 | DISTANCE_SENSOR | 29 | 0.48 | 12.1 | 25.0 |  |
| 24 | 436 | CURRENT_MODE | 29 | 0.48 | 9.7 | 20.0 |  |
| 25 | 411 | CURRENT_EVENT_SEQUENCE | 19 | 0.32 | 4.1 | 13.0 |  |
| 26 | 241 | VIBRATION | 5 | 0.08 | 2.7 | 32.0 |  |
| 27 | 4 | PING | 5 | 0.08 | 1.7 | 20.0 |  |

## Headline numbers (n = 60 s, method above)

- **L = 2300.4 B/s** (total offered, wire bytes).
- **L_crit = 1359.4 B/s** = ATTITUDE 588.0 + ATTITUDE_QUATERNION 431.9 + GLOBAL_POSITION_INT 191.1 +
  SYS_STATUS 50.3 + LOCAL_POSITION_NED 38.7 + BATTERY_STATUS 25.6 + HEARTBEAT 20.3 +
  EXTENDED_SYS_STATE 13.5. (59.1 % of L; ATTITUDE+ATTITUDE_QUATERNION alone = 1019.9 B/s.)
- **Top five chattiest:** ATTITUDE (588.0), ATTITUDE_QUATERNION (431.9), GPS_RAW_INT (274.4),
  GLOBAL_POSITION_INT (191.1), VFR_HUD (113.6) — together 1599.0 B/s = 69.5 % of L.
- **UART fractions:** L / 11520 B/s (115200 8N1) = **20.0 %**; L / 46080 B/s (460800) = **5.0 %**.
  L_crit / 11520 = 11.8 %.
- **RADIO_STATUS:** not present in PX4's stream (expected: no radio in the loop; DroneBridge will inject
  its own on the ground side).
- **Real-time factor:** 0.981 = delta(ATTITUDE.time_boot_ms) / delta(host monotonic ms) over the same
  60 s (n = 882 ATTITUDE samples, first-to-last). Corroborated: rates sit ~2 % under nominal
  (ATTITUDE 14.70 vs 15 Hz, HEARTBEAT 58/60 s; probe511 baseline 177/12 s = 14.75 Hz). PX4 log says
  "Simulation with 1.0x speedup"; SIH runs on PX4's lockstep scheduler paced by wall time, so PX4
  time runs ~2 % slow vs host wall clock. Close to 1, but latency/rate numbers stamped in PX4 time
  should be scaled by 0.98 if compared with host-clock measurements.

## Context: the default GCS instance is ~7x heavier (do not shuttle it)

Instance #0 (`px4-rc.mavlink`: udp 18570 -> guest localhost:14550, `-r 4000000`, plus 50 Hz overrides
for ATTITUDE/ATTITUDE_QUATERNION/GLOBAL_POSITION_INT/LOCAL_POSITION_NED/POSITION_TARGET_LOCAL_NED/
ATTITUDE_TARGET/SERVO_OUTPUT_RAW) measured in-guest for 10 s (`tools/mavframes.py`, n = 10 s, 12:35 PDT):
~16.7 kB/s total = 145 % of a 115200 UART. That is why the shuttle uses its own Normal-mode instance.

## PX4 txbuf flow control (grep of `src/modules/mavlink/`, guest)

1. Yes, but opt-in: `Mavlink::update_radio_status()` (mavlink_main.cpp:1365-1392) scales a per-instance
   `_radio_status_mult` from RADIO_STATUS.txbuf: x0.80 if txbuf < 25 %, x0.975 if < 35 %, x1.025 if > 50 %,
   clamped 0.01-1.0; it multiplies all non-constant stream rates via `hardware_mult` in `update_rate_mult()`.
2. Only when `_use_software_mav_throttling` is set: `mavlink start ... -s` (CLI) or `MAV_${i}_RADIO_CTL`
   (configured serial instances). Our instance is started without `-s` => txbuf is **ignored** for rate
   scaling (RADIO_STATUS is still received/published; a timeout of `MAV_RADIO_TOUT` resets the mult).
3. Independently, a non-zero tx error rate (send failures) scales rates down; UDP status shows
   "flow control: OFF", "tx rate mult: 1.000". Caveat: if `-s` is ever added, DroneBridge's injected
   RADIO_STATUS (txbuf = free %) would start throttling PX4 — decide that deliberately.
