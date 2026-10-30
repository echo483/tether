# T0-REPORT — PX4 SIH software substrate (2026-10-30, 12:33–12:48 PDT)

Scope: T1-PROMPT phases 2–4 (+ native probe and shuttle). Hardware phases 1/5 not touched.
Host Debian 13 (glibc 2.41); VM `dronelab` Ubuntu 24.04 (glibc 2.39), PX4 v1.16.2, passt networking.
Mullvad at report time: `Disconnected`, LAN sharing `allow` (guest<->host traffic worked throughout;
Mullvad was not a factor). Raw evidence: `notes/evidence/`. Run everything from `~/drone-labs/tether`.

| Phase | Result | One-line evidence |
|---|---|---|
| A SIH headless in VM, HB + ATTITUDE | **PASSED** | in-guest 10 s: HEARTBEAT n=10, ATTITUDE n=490 (49 Hz) on instance #0 |
| B guest->host + return path | **PASSED** | host got stream from localhost:14556; PARAM_VALUE x3 + COMMAND_ACK x2 came back; no UDP portForward needed |
| C cmd 511 probe | **PASSED** | ACK=ACCEPTED; ATTITUDE 177/12 s -> 11/12 s -> 177/12 s after restore |
| D 60 s census | **PASSED** | L = 2300.4 B/s, L_crit = 1359.4 B/s, n = 60 s / 3340 packets |
| E native PX4 on host | **FAILED (gate)** | `bin/px4` links libgz-transport13/gz-msgs10/gz-utils2 (absent on host) -> not copied, not run |
| F UDP<->serial shuttle vs pty | **PASSED** | 23255 B through pty in 10 s, 0 BAD_DATA, HB n=10, ATT n=148, PARAM_VALUE round trip via serial |

## Phase A — PX4 SIH headless (PASSED)
- Commands: `tools/vmssh 'bash -s' < tools/guest_px4_sih.sh` (wraps:
  `cd ~/PX4-Autopilot/build/px4_sitl_default/rootfs && PX4_SIM_MODEL=sihsim_quadx ../bin/px4 -i 0` in tmux `px4`).
  In-guest check: `tools/vmssh 'python3 - 14550 10' < tools/mavframes.py`.
- Observed: log `SIH simulator`, `Simulation loop with 250 Hz`, `1.0x speedup`, `Ready for takeoff!`.
  Instance #0 in-guest (10 s, stdlib frame splitter): HEARTBEAT n=10 (1.0 Hz), ATTITUDE n=490 (49.0 Hz).
- RTF = **0.981** (host, 60 s, delta ATTITUDE.time_boot_ms / delta host monotonic, n=882 samples;
  a 5 s re-check on instance #5 gave 0.974). Close to 1 but PX4 time runs ~2 % slow vs host wall clock;
  stream rates are ~2 % under nominal for the same reason. Not rebuilt; SIH target was already built.

## Phase B — guest->host and return path (PASSED)
- Command: TETHER instance `px4-mavlink start -u 14556 -o 14560 -t $GW -r 400000`, `GW` computed in the
  guest from `ip route` (never hardcoded). Host: `uv run python tools/mavframes.py 14560 10`.
- Observed: host received from source **localhost:14556** (passt maps guest->gateway to the host loopback
  and preserves the guest source port). Return path: replies sent from the same host socket to that source
  landed in PX4: 3 PARAM_REQUEST_READ -> 3 PARAM_VALUE, 2x cmd 511 -> 2 COMMAND_ACK. PX4 `mavlink status`
  for instance #5: `rx: 65.7 B/s`, `partner IP: <guest gateway>`, `GCS heartbeat valid`
  (`notes/evidence/mavlink-status-inst5.txt`).
- The claim "no portForward needed, NAT mapping kept alive by the stream" **held**. No VM edit needed.

## Phase C — cmd 511 probe (PASSED)
- Command: `~/.local/bin/uv run python tools/probe511.py --port 14560 --window 12` (one socket bound to
  localhost:14560; learns PX4's source from the first datagram, replies to it).
- Observed (`notes/evidence/probe511.json.txt`), ATTITUDE (msgid 30, sysid 1), 12 s windows, 2 s settle:
  baseline **n=177 (14.75 Hz)** -> after `511(30, 1000000 us)` ACK result 0 = ACCEPTED, **n=11 (0.92 Hz)**
  -> after `511(30, 0)` ACK ACCEPTED, **n=177 (14.75 Hz)** (restored exactly).
- Instance that received it: **#5, mode Normal, UDP 14556 -> remote 14560, partner = guest gateway**.
  Control: instance #0 measured in-guest *during* the 1 Hz window still had ATTITUDE n=392/8 s (49 Hz)
  (`notes/evidence/probe511-inst0-control.txt`) — 511 is per-instance, as expected.
- RADIO_STATUS: not present in PX4's stream (no radio in loop).

## Phase D — census (PASSED) — details in `notes/census.md`
- Command: `uv run python tools/census.py --port 14561 --secs 60` on clone instance #6 (identical flags
  to #5) because a QGroundControl (pid 28531, not mine; later exited) held host UDP 14560 and was attached
  to #5. 5 s cross-check on #5 itself afterwards: L = 2312.6 B/s (agrees within 0.5 %).
- **L = 2300.4 B/s; L_crit = 1359.4 B/s**; 20.0 % of 115200 baud (11520 B/s), 5.0 % of 460800 (46080 B/s).
- Top 5: ATTITUDE 588.0, ATTITUDE_QUATERNION 431.9, GPS_RAW_INT 274.4, GLOBAL_POSITION_INT 191.1, VFR_HUD 113.6 B/s.
- Default instance #0 (50 Hz overrides) offers ~16.7 kB/s (in-guest 10 s) = 145 % of a 115200 UART — do not shuttle it.
- txbuf flow control: exists (RADIO_STATUS.txbuf scales `_radio_status_mult`) but only with `mavlink start -s`
  / `MAV_x_RADIO_CTL`; our instance has it OFF.
- Failsafe params (read live via PARAM_REQUEST_READ through the shuttle socket; defaults from the build's
  `parameters.json`): **NAV_DLL_ACT = 0 (default 0, Disabled)**, **COM_DL_LOSS_T = 10 s (default 10)**,
  **COM_DLL_EXCEPT = 0 (default 0)**. With NAV_DLL_ACT = 0 a GCS/link loss does not trigger a failsafe
  (observed: `Connection to ground station lost` logged when QGC left; vehicle unaffected).
  Also noted: NAV_RCL_ACT default 2 (Return) on RC loss; COM_RC_IN_MODE default 3.

## Phase E — native PX4 on the host (FAILED at the gate; nothing copied)
- Command: `tools/vmssh 'ldd ~/PX4-Autopilot/build/px4_sitl_default/bin/px4'` (`notes/evidence/guest-grep-ldd.txt`).
- Non-libc deps: **libgz-transport13, libgz-msgs10, libgz-utils2** (Gazebo), libprotobuf.so.32, libzmq.so.5,
  libuuid, libz, libbsd, libsodium, libpgm-5.3, libnorm, libgssapi_krb5/libkrb5/libk5crypto/libcom_err/
  libkrb5support/libkeyutils, libresolv, libmd. Host `/sbin/ldconfig -p` has **all of these except the 3 gz
  libs** (checked one by one). Per the brief (copy only if deps are standard libs) I did not copy or run it.
- Assumption that proved false: "the SITL binary only needs libc++" — the default build links the Gazebo bridge.
- Untested options for later (each needs a decision): (a) scp just the 3 gz .so files from the guest into
  `~/.local/opt/px4-sih/lib` along with bin/ + etc/, and run with `LD_LIBRARY_PATH` (guest glibc 2.39 < host
  2.41, so likely OK; small job, maybe 10 min);
  (b) a gz-free build (`boards/px4/sitl/` has default/nolockstep/... configs, no dedicated sih one) — a new
  build, not done. Venue demo therefore still needs the VM.

## Phase F — shuttle (PASSED against a pty; not tested on real hardware)
- `tools/shuttle_passthrough.py` (110 lines, stdlib + pyserial): UDP bind (default localhost:14560), learns
  PX4 source from the first datagram, bounded queue K = `--queue-max` (default 2048 B ≈ 178 ms at 115200)
  with drop-oldest-whole-datagram, writes paced at baud/10 B/s and kernel out-queue capped at 256 B,
  serial->UDP unparsed from the same socket, `--hold-reset` default ON (dtr=False, rts=True set before
  `open()`), 1 Hz status line.
- Test: `uv run python tools/test_shuttle_pty.py --port 14561 --secs 10` (os.openpty pair; master side parses
  with pymavlink CRC checks, injects PARAM_REQUEST_READ). 115200: 23255 B in 10.0 s (2320 B/s ≈ L),
  BAD_DATA = 0, HEARTBEAT n=10, ATTITUDE n=148, 28 msg types, PARAM_VALUE(NAV_DLL_ACT) returned at 3.02 s,
  drops 0. Overload check at `--baud 9600` (960 B/s < L): queue stayed ≤ 2048 B, 191 datagrams / 7698 B
  dropped, output 957 B/s, BAD_DATA = 0 (framing intact), PARAM_VALUE still round-tripped.
  Evidence: `notes/evidence/shuttle-pty-{115200,9600}.txt`.
- Not tested: real CP2102/ESP32 port (ops is not in `dialout`), the hold-reset line behaviour on real hardware.

## Port map actually in use — see table in `notes/sitl.md`
Host side: TCP localhost:2222 -> guest 22 (ssh); UDP localhost:14560 <- PX4 #5 (guest 14556, TETHER/shuttle);
UDP localhost:14561 <- PX4 #6 (guest 14557, census/test clone). Gimbal instance #3 (13030) was stopped to
free the 6-instance limit. QGC for the demo should stay on 14550 (WLAN/DroneBridge), never on 14560.

## Assumptions that proved false / gotchas
- `mavlink start -m normal` is invalid in PX4 1.16 (omit `-m`).
- `px4-mavlink ...` client output goes to the PX4 tmux console, not the calling shell.
- PX4 SITL caps at 6 mavlink instances (5 used by default rcS).
- Any dotted-quad literal written by the agent tooling becomes `[IP_ADDRESS]`; tools use `localhost` and
  compute the gateway at runtime. `tools/rf_probe.py` (not written by me) still contains that placeholder
  at lines 6, 7, 16 and will fail as-is.

## State left
VM `dronelab` running; PX4 SIH running in guest tmux `px4` with instances #5 (14556->14560) and #6
(14557->14561) active; no native PX4 process; no host processes left running by me.
