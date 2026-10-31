#!/usr/bin/env python3
"""mission_bay.py — the Fort Mason bay mission: upload, arm, start, watch. A second GCS behind ground.py.

    ground.py ... --mirror localhost:14571          # ground.py copies the downlink here and forwards our replies
    uv run python tools/mission_bay.py --upload-only # upload only (vehicle on the ground at home)
    uv run python tools/mission_bay.py --go          # upload + AUTO.MISSION + arm (+ MISSION_START if needed)
    uv run python tools/mission_bay.py --go --watch  # ... then print mode/armed/range/alt/landed 1 Hz until disarmed
    uv run python tools/mission_bay.py --watch       # watch only
    uv run python tools/mission_bay.py --rtl         # manual RTL x3 straight into air.py's command link (:14598)

Transport: we bind udpin localhost:MIRROR (default 14571) and read PX4's replies from ground.py's mirror of the
downlink; pymavlink answers to the datagram source = ground.py's mirror socket, and ground.py forwards that to the
command link (localhost:14598 -> air.py -> PX4, never squeezed). Run the upload while the drone sits at home (range
< 250 m = unlimited capacity), i.e. before any squeeze. --rtl does not need the mirror at all.

Mission (mission_type 0, MISSION_ITEM_INT, frame GLOBAL_RELATIVE_ALT_INT): takeoff to --alt at home;
DO_CHANGE_SPEED --speed m/s; waypoints due north over the bay at --legs metres (lat += m/111111); the last leg is
NAV_LOITER_UNLIM (hold). Deliberately NO RTL at the end: without TETHER the drone stays out in the blackout.
"""
import argparse
import math
import os
import sys
import time

os.environ.setdefault("MAVLINK20", "1")                  # mission_type is a MAVLink 2 extension field
from pymavlink import mavutil  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tnet  # noqa: E402

M = mavutil.mavlink
MAIN = {1: "MANUAL", 2: "ALTCTL", 3: "POSCTL", 4: "AUTO", 5: "ACRO", 6: "OFFBOARD", 7: "STAB", 8: "RATTITUDE"}
SUB = {1: "READY", 2: "TAKEOFF", 3: "LOITER", 4: "MISSION", 5: "RTL", 6: "LAND", 8: "FOLLOW", 9: "PRECLAND"}
LANDED = {0: "?", 1: "ON_GROUND", 2: "IN_AIR", 3: "TAKEOFF", 4: "LANDING"}

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--mirror-port", type=int, default=14571)
ap.add_argument("--upload-only", action="store_true")
ap.add_argument("--go", action="store_true", help="upload, then AUTO.MISSION + arm")
ap.add_argument("--watch", action="store_true", help="print state 1 Hz until the vehicle disarms after flying")
ap.add_argument("--watch-s", type=float, default=420.0)
ap.add_argument("--rtl", action="store_true", help="send RTL x3 straight to the command link and exit")
ap.add_argument("--alt", type=float, default=40.0)
ap.add_argument("--speed", type=float, default=15.0)
ap.add_argument("--legs", default="300,600,900,1100", help="metres north of home; the last one is a hold")
ap.add_argument("--sysid", type=int, default=245, help="our GCS sysid (QGC is 255)")
a = ap.parse_args()
T0 = time.time()


def say(*x):
    print(f"[{time.time() - T0:6.1f}s]", *x, flush=True)


if a.rtl:                                                # no mirror needed: commands ride the separate link
    c = mavutil.mavlink_connection(f"udpout:{tnet.LOCAL}:{tnet.AIR_UPLINK_PORT}", source_system=a.sysid,
                                   source_component=190)
    for _ in range(3):
        c.mav.command_long_send(1, 1, M.MAV_CMD_NAV_RETURN_TO_LAUNCH, 0, 0, 0, 0, 0, 0, 0, 0)
        time.sleep(0.3)
    say("RTL x3 sent to the command link")
    sys.exit(0)

if a.go:                                                 # fresh flight: re-arm ground.py's latch-once RTL failsafe
    import json, socket
    socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(json.dumps({"failsafe_reset": True}).encode(),
                                                             (tnet.LOCAL, tnet.GROUND_CTRL_PORT))
c = mavutil.mavlink_connection(f"udpin:{tnet.LOCAL}:{a.mirror_port}", source_system=a.sysid, source_component=190)
c.mav.robust_parsing = True
ST = dict(hb=None, armed=None, mode="?", home=None, pos=None, alt=None, landed=0, t_hb=0.0)
next_hb = 0.0


def mode_name(cm):
    main, sub = (cm >> 16) & 0xFF, (cm >> 24) & 0xFF
    return f"{MAIN.get(main, main)}.{SUB.get(sub, sub)}" if main == 4 else MAIN.get(main, str(main))


def pump(timeout=0.1, want=None):
    """Read the mirror; keep state; print STATUSTEXT; send our GCS heartbeat 1 Hz. Return first msg of type `want`."""
    global next_hb
    end = time.time() + timeout
    while True:
        now = time.time()
        if now >= next_hb and c.last_address:            # udpin can only reply once it has heard ground.py
            next_hb = now + 1.0
            c.mav.heartbeat_send(M.MAV_TYPE_GCS, M.MAV_AUTOPILOT_INVALID, 0, 0, 0)
        m = c.recv_match(blocking=True, timeout=max(0.0, min(0.1, end - now)))
        if m is not None:
            t, src = m.get_type(), (m.get_srcSystem(), m.get_srcComponent())
            if t == "HEARTBEAT" and src == (1, 1):
                ST.update(hb=m, armed=bool(m.base_mode & M.MAV_MODE_FLAG_SAFETY_ARMED), mode=mode_name(m.custom_mode),
                          t_hb=now)
            elif t == "GLOBAL_POSITION_INT" and src == (1, 1) and (m.lat or m.lon):
                ST["pos"], ST["alt"] = (m.lat / 1e7, m.lon / 1e7), m.relative_alt / 1000.0
            elif t == "HOME_POSITION" and src == (1, 1):
                ST["home"] = (m.latitude / 1e7, m.longitude / 1e7)
            elif t == "EXTENDED_SYS_STATE":
                ST["landed"] = m.landed_state
            elif t == "STATUSTEXT":
                say(f"STATUSTEXT {src[0]}/{src[1]} sev{m.severity}: {m.text}")
            if want and t in want and getattr(m, "target_system", a.sysid) in (a.sysid, 0):
                return m
        if time.time() >= end:
            return None


def rng():
    if not (ST["home"] and ST["pos"]):
        return None
    (la0, lo0), (la, lo) = ST["home"], ST["pos"]
    return 6371000.0 * math.hypot(math.radians(la - la0), math.radians(lo - lo0) * math.cos(math.radians(la0)))


def command(cmd, *p, tries=3, wait=1.5):
    p = (list(p) + [0.0] * 7)[:7]
    for i in range(tries):
        c.mav.command_long_send(1, 1, cmd, i, *p)
        end = time.time() + wait
        while time.time() < end:
            m = pump(end - time.time(), want=("COMMAND_ACK",))
            if m is not None and m.command == cmd:
                return m.result
    return None


say(f"listening on udpin {tnet.LOCAL}:{a.mirror_port} (ground.py --mirror {tnet.LOCAL}:{a.mirror_port})")
end = time.time() + 15
while ST["hb"] is None and time.time() < end:
    pump(0.5)
if ST["hb"] is None:
    sys.exit("FAIL: no PX4 HEARTBEAT on the mirror — is ground.py running with --mirror localhost:%d?" % a.mirror_port)
end = time.time() + 6
while (ST["home"] is None or ST["pos"] is None) and time.time() < end:
    pump(0.5)
if ST["home"] is None:
    ST["home"] = ST["pos"]
    say("no HOME_POSITION seen; using current position as home")
say(f"PX4 up: mode {ST['mode']} armed {ST['armed']} home {ST['home']} alt {ST['alt']}")

if a.go or a.upload_only:
    la0, lo0 = ST["home"]
    legs = [float(x) for x in a.legs.split(",")]
    F, FM = M.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, M.MAV_FRAME_MISSION
    items = [(F, M.MAV_CMD_NAV_TAKEOFF, (0, 0, 0, float("nan")), la0, lo0, a.alt),
             (FM, M.MAV_CMD_DO_CHANGE_SPEED, (1, a.speed, -1, 0), None, None, 0.0)]
    for i, d in enumerate(legs):
        last = i == len(legs) - 1
        items.append((F, M.MAV_CMD_NAV_LOITER_UNLIM if last else M.MAV_CMD_NAV_WAYPOINT,
                      (0, 0, 0, float("nan")), la0 + d / 111111.0, lo0, a.alt))

    def item(seq):
        fr, cmd, (p1, p2, p3, p4), la, lo, z = items[seq]
        return M.MAVLink_mission_item_int_message(1, 1, seq, fr, cmd, 0, 1, p1, p2, p3, p4,
                                                  int(round((la or 0) * 1e7)), int(round((lo or 0) * 1e7)), z, 0)
    ok = False
    for attempt in range(5):
        c.mav.mission_count_send(1, 1, len(items), 0)
        say(f"MISSION_COUNT {len(items)} sent (attempt {attempt + 1})")
        sent, end = set(), time.time() + 8
        while time.time() < end:
            m = pump(1.5, want=("MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"))
            if m is None:
                if not sent:
                    break                                # nothing asked: resend the count
                continue
            if getattr(m, "mission_type", 0) != 0:
                continue
            if m.get_type() == "MISSION_ACK":
                ok = m.type == M.MAV_MISSION_ACCEPTED
                say(f"MISSION_ACK type {m.type} ({'ACCEPTED' if ok else 'REJECTED'}) after {len(sent)} items")
                break
            if 0 <= m.seq < len(items):
                c.mav.send(item(m.seq)); sent.add(m.seq)  # noqa: E702
                fr, cmd, _, la, lo, z = items[m.seq]
                say(f"  item {m.seq}: cmd {cmd}" + (f" {la:.6f},{lo:.6f} {z:.0f} m" if la else ""))
        if ok:
            break
    if not ok:
        sys.exit("FAIL: mission upload not acknowledged")
    say(f"mission uploaded: takeoff {a.alt:.0f} m, speed {a.speed:.0f} m/s, legs {legs} m north (last = hold), no RTL")

if a.go:
    r = command(M.MAV_CMD_DO_SET_MODE, M.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 4, 4)
    say(f"set AUTO.MISSION -> ack {r}")
    for attempt in range(12):                            # preflight 'GPS drift' can deny arming for ~1 min
        r = command(M.MAV_CMD_COMPONENT_ARM_DISARM, 1)
        pump(1.0)
        say(f"arm attempt {attempt + 1} -> ack {r}; armed {ST['armed']} mode {ST['mode']}")
        if ST["armed"]:
            break
        pump(4.0)
    if not ST["armed"]:
        sys.exit("FAIL: arming denied (see STATUSTEXT above)")
    pump(2.0)
    if ST["mode"] != "AUTO.MISSION":
        say(f"mode is {ST['mode']}: sending MISSION_START -> ack {command(M.MAV_CMD_MISSION_START, 0, 0)}")
    say(f"GO: armed, mode {ST['mode']}")

if a.watch:
    flew, end, nxt = bool(ST["armed"]), time.time() + a.watch_s, 0.0
    while time.time() < end:
        pump(0.2)
        now = time.time()
        if now >= nxt:
            nxt = now + 1.0
            d = rng()
            say(f"mode {ST['mode']:<13} armed {ST['armed']!s:<5} range {'—' if d is None else f'{d:6.0f}'} m  "
                f"alt {'—' if ST['alt'] is None else f'{ST['alt']:5.1f}'} m  landed {LANDED.get(ST['landed'])}  "
                f"hb_age {now - ST['t_hb']:.1f} s")
        flew = flew or bool(ST["armed"])
        if flew and ST["armed"] is False and now - ST["t_hb"] < 2:
            say("vehicle DISARMED — done")
            break
