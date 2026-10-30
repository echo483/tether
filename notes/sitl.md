# sitl.md — PX4 SIH substrate for TETHER (copy-paste commands)

PX4 v1.16.2, VM `dronelab` (Ubuntu 24.04, 8 vCPU, `qemu:///session`, passt networking), build
`~/PX4-Autopilot/build/px4_sitl_default` in the guest (already built; SIH airframe `10040_sihsim_quadx`;
NOT rebuilt). Verified 2026-10-30 12:35–12:45 PDT. All commands run on the host from `~/drone-labs/tether`.
No IP literal appears anywhere: the host is `localhost`, the guest gateway is computed in the guest.

## PRIMARY (only working path): PX4 SIH in the VM

Native-on-host PX4 is NOT available (Phase E failed its gate: the VM's `bin/px4` links Gazebo
libs `libgz-transport13`, `libgz-msgs10`, `libgz-utils2`, which the Debian host does not have). See T0-REPORT.

```bash
cd ~/drone-labs/tether

# 1. start the VM (no-op error if already running) and wait for ssh (boot ~30-60 s)
LIBVIRT_DEFAULT_URI=qemu:///session virsh start dronelab
until tools/vmssh true 2>/dev/null; do sleep 3; done; echo VM up

# 2. start PX4 SIH headless in guest tmux "px4" + the TETHER mavlink instance aimed at the gateway
#    (idempotent; gateway = `ip route | awk '/default/{print $3; exit}'` computed IN the guest)
tools/vmssh 'bash -s' < tools/guest_px4_sih.sh

# 3. check from the host: HEARTBEAT ~1 Hz and ATTITUDE ~15 Hz from source localhost:14556
~/.local/bin/uv run python tools/mavframes.py 14560 10
```

What `tools/guest_px4_sih.sh` runs inside the guest (manual equivalent):

```bash
# in the guest (tools/vmssh, or: ssh -4 -p 2222 -i ~/.ssh/drone_lab_ed25519 lab@localhost)
cd ~/PX4-Autopilot/build/px4_sitl_default/rootfs
tmux new-session -d -s px4 -x 200 -y 50 \
  "cd $PWD && PX4_SIM_MODEL=sihsim_quadx ../bin/px4 -i 0 2>&1 | tee /tmp/px4-sih.log"
sleep 10   # until /tmp/px4-sih.log shows "Startup script returned successfully" / "Ready for takeoff!"
GW=$(ip route | awk '/default/{print $3; exit}')
../bin/px4-mavlink start -u 14556 -o 14560 -t "$GW" -r 400000     # TETHER instance (Normal mode)
```

Notes:
- `-m normal` is rejected by PX4 ("invalid mode"); omitting `-m` gives Normal mode.
- `px4-mavlink` client commands print to the **PX4 console** (tmux pane), not the ssh session. Read
  with `tools/vmssh 'tmux capture-pane -p -t px4 -S -300'`.
- PX4 allows max 6 mavlink instances; the default rcS uses 5 (#0-#4) and the TETHER instance is #5.
  To add the census/test clone (`-u 14557 -o 14561`) I first stopped the unused gimbal instance:
  `tools/vmssh 'cd ~/PX4-Autopilot/build/px4_sitl_default/rootfs; ../bin/px4-mavlink stop -u 13030;
  ../bin/px4-mavlink start -u 14557 -o 14561 -t $(ip route | awk "/default/{print \$3; exit}") -r 400000'`
- Attach to the PX4 shell: `ssh -4 -t -p 2222 -i ~/.ssh/drone_lab_ed25519 lab@localhost tmux attach -t px4`
  (detach: Ctrl-b d). `Ready for takeoff!` appears without any GCS (NAV_DLL_ACT = 0).
- At the venue the gateway changes; nothing needs editing because the scripts compute it. If the
  network changes while PX4 is running, re-run step 2 after restarting PX4 (the instance keeps the old -t).

## Port map in use (all UDP)

| PX4 inst | mode | guest bind | sends to | host side | purpose |
|---|---|---|---|---|---|
| #0 | Normal, -r 4 MB/s, 50 Hz overrides | 18570 | guest localhost:14550 | (not reachable) | default GCS, in-guest only |
| #1 | Onboard | 14580 | guest localhost:14540 | — | offboard API |
| #2 | Onboard | 14280 | guest localhost:14030 | — | payload |
| #3 | Gimbal | 13030 | guest localhost:13280 | — | **stopped** to free a slot |
| #4 | Custom (SIH display) | 19450 | guest localhost:19410 | — | HIL_* to SIH viewer |
| #5 | Normal, -r 400000 | 14556 | guest gateway:14560 | localhost:14560 (src localhost:14556) | **TETHER shuttle** |
| #6 | Normal, -r 400000 | 14557 | guest gateway:14561 | localhost:14561 (src localhost:14557) | census / pty-test clone |
| — | TCP portForward | guest 22 | — | localhost:2222 | ssh |

Under passt, guest -> gateway arrives on the host loopback with the guest source port preserved, and
host replies to that source go back to the PX4 instance (verified; no UDP portForward needed).

## Shuttle (Phase F) usage

```bash
~/.local/bin/uv run python tools/shuttle_passthrough.py --dev /dev/serial/by-path/<adapter> \
    --port 14560 --baud 115200            # --no-hold-reset for a non-ESP32 adapter
~/.local/bin/uv run python tools/test_shuttle_pty.py --port 14561   # pty self-test, no hardware
```
Only one process can own host UDP 14560: do not run QGC with a UDP link on 14560 at the same time
(a QGC instance was bound there during this session). For QGC on the host directly against SITL,
give QGC a UDP link on port 14561 (the clone) instead.

## Stop (not exercised this session — PX4 was left running on purpose)

```bash
tools/vmssh 'tmux send-keys -t px4 "shutdown" Enter'; sleep 3
tools/vmssh 'pgrep -af "[b]in/px4" || echo px4 stopped; tmux kill-session -t px4 2>/dev/null; true'
LIBVIRT_DEFAULT_URI=qemu:///session virsh shutdown dronelab     # only if the VM is no longer needed
```

## Phase A evidence (in-guest, 12:35 PDT)
Instance #0 listened 10 s inside the guest with `tools/vmssh 'python3 - 14550 10' < tools/mavframes.py`:
HEARTBEAT n=10 (1.0 Hz), ATTITUDE n=490 (49.0 Hz), ATTITUDE_QUATERNION n=490, GLOBAL_POSITION_INT n=490.
PX4 log: `SIH simulator`, `Simulation loop with 250 Hz`, `Simulation with 1.0x speedup`, `Ready for takeoff!`.
RTF measured on the host over 60 s: 0.981 (see census.md).
