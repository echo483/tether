#!/usr/bin/env python3
"""ground.py — TETHER ground agent: radio -> QGC, staleness metrics (CONTRACT §2), built-in manager (cmd 511).

    ~/.local/bin/uv run python -u tools/ground.py [--manager]                  # emulated: udp 0.0.0.0:14550
    ~/.local/bin/uv run python -u tools/ground.py --serial /dev/serial/by-path/<board3> [--manager]
    sweep.py --launch: ground.py --log DIR/ground.jsonl [--manager]            # default log logs/live/ground.jsonl
    live toggle: UDP JSON {"manager": true|false} -> localhost:tnet.GROUND_CTRL_PORT (off = restore all streams)
    --failsafe (bay demo): with the manager on, latch-once RTL (cmd 20 x3) when every sheddable tier is shed and
      picture_age > 1 s for 3 s, or the downlink is blackout for 2 s. ctl {"failsafe_reset": true} | {"failsafe": bool}
    --uplink HOST[:PORT]: where the command link goes (default localhost:14598; laptop 1's IP in a two-laptop split)

Radio -> QGC raw; QGC replies -> AIR_UPLINK_PORT raw. compid 68 never counted; goodput = decoded frames only.
Operator sees TETHER in QGC as sysid 1/comp 191: STATUSTEXT on shed/restore, NAMED_VALUE_FLOAT PIC_AGE+TIER 2 Hz.
Clock: PX4 SIH time runs ~3 % slow vs host, so the 30 s running-min offset projects each sample to now by a measured
skew r (lower envelope of 1 s ATTITUDE minima, calm buckets); a plain 30 s min would read ~1 s of fake qdelay.
"""
import argparse, json, select, signal, socket, sys, time  # noqa: E401
from collections import deque
from contextlib import suppress
from pathlib import Path

import numpy as np
from pymavlink.dialects.v20 import common as mav2

ROOT = (HERE := Path(__file__).resolve().parent).parent
sys.path.insert(0, str(HERE))
import tnet  # noqa: E402  — CONTRACT §1 port map
from qsim import DEFAULT_TIERS  # noqa: E402  — tier 0/1 lists; tier 2 = everything else in the census

POLICY_PATH, SKEW_PATH = ROOT / "policy.json", ROOT / tnet.LIVE_DIR / "ground-skew.json"
DB_COMPID, OFFSET_WIN, SKEW_WIN, CALM_S, STALE_S, BLACKOUT_S = 68, 30.0, 120.0, 0.1, 1.0, 1.0
EXTRA_IDS = {"LINK_NODE_STATUS": 8, "TIME_ESTIMATE_TO_TARGET": 380, "CURRENT_EVENT_SEQUENCE": 411, "CURRENT_MODE": 436}
# failsafe (--failsafe, manager on): stale-with-everything-shed for FS_STALE_T, or blackout for FS_BO_T -> RTL x3
MAV_CMD_NAV_RETURN_TO_LAUNCH, FS_STALE_T, FS_BO_T, FS_SENDS, FS_GAP_S = 20, 3.0, 2.0, 3, 0.3
FS_FRESH_S, FS_RESET_FRESH_T = 0.3, 10.0         # re-arm: fresh this long, then a manager toggle (or ctl reset)

from pymavlink.dialects.v20 import development as dev  # noqa: E402  names only (validation); parsing = common
MSG_IDS = {**{c.msgname: i for i, c in dev.mavlink_map.items()}, **{c.msgname: i for i, c in mav2.mavlink_map.items()},
           **EXTRA_IDS}      # + development-dialect ids seen in the census, absent from pymavlink 2.4.50
ID_NAMES = {i: n for n, i in MSG_IDS.items()}

def default_policy():
    rows = json.loads((ROOT / "notes/evidence/census-14561.json").read_text())["rows"]
    listed = {n for t in DEFAULT_TIERS for n in t}
    rest = [n for n in (ID_NAMES.get(r["msgid"], r["name"]) for r in rows) if n not in listed]
    return {"name": "default", "tiers": [list(t) for t in DEFAULT_TIERS] + [rest],
            "q_hi_s": 0.5, "q_lo_s": 0.1, "T_detect_s": 0.6, "T_restore_s": 3.0}

def validate_policy(p):
    """[] if ok, else reasons (CONTRACT §3: known msg names only, tier 0 holds HEARTBEAT + ATTITUDE)."""
    tiers = p.get("tiers") if isinstance(p, dict) else None
    if not (isinstance(tiers, list) and tiers and all(isinstance(t, list) for t in tiers)):
        return ["tiers must be a non-empty list of lists"]
    names = [n for t in tiers for n in t]
    errs = [f"tier 0 lacks {n}" for n in ("HEARTBEAT", "ATTITUDE") if n not in tiers[0]]
    errs += [f"unknown MAVLink message {n!r}" for n in names if n not in MSG_IDS]
    errs += [f"{n} in more than one tier" for n in sorted({n for n in names if names.count(n) > 1})]
    errs += [f"{k} must be a positive number" for k in ("q_hi_s", "q_lo_s", "T_detect_s", "T_restore_s")
             if not isinstance(p.get(k), (int, float)) or p[k] <= 0]
    return errs or (["q_lo_s must be < q_hi_s"] if p["q_lo_s"] >= p["q_hi_s"] else [])

def frame_header(buf):
    """(seq, sysid, compid, msgid) from the raw frame (MAVLink_unknown carries no parsed header)."""
    return (buf[4], buf[5], buf[6], buf[7] | buf[8] << 8 | buf[9] << 16) if buf[0] == 0xFD else tuple(buf[2:6])

class Clock:
    """Per-type offset = min over the last 30 s of (t_rx − time_boot_ms/1000), each sample projected to now by r."""
    def __init__(self, t0):
        self.t0, self.samp, self.buckets, self.cur, self.line, self.r = t0, {}, deque(), None, None, 0.0
        with suppress(OSError, ValueError, KeyError, TypeError):   # prior from the last run until 5 calm buckets
            r = json.loads(SKEW_PATH.read_text())["r"]
            self.r = r if abs(r) < 0.1 else 0.0
    def offset(self, name, t):
        q = self.samp.get(name)
        return min(d + self.r * (t - ti) for ti, d in q) if q else None
    def add(self, name, t, tbm_s):
        d, q = t - tbm_s, self.samp.setdefault(name, deque())
        q.append((t, d))
        while len(q) > 1 and q[0][0] < t - OFFSET_WIN:
            q.popleft()
        if name == "ATTITUDE":
            b = int(t - self.t0)
            if self.cur and self.cur[0] != b:
                self.buckets.append(self.cur[1:])
                while self.buckets[0][0] < self.buckets[-1][0] - SKEW_WIN:
                    self.buckets.popleft()
                self.refit()
            if not self.cur or self.cur[0] != b or d < self.cur[2]:
                self.cur = (b, t - self.t0, d)
        return d - self.offset(name, t)                  # qdelay of this frame
    def refit(self):
        pts = np.array(self.buckets)
        if self.line is not None:                        # calm only: a squeezed queue sits far above the line
            pts = pts[pts[:, 1] - np.polyval(self.line, pts[:, 0]) < CALM_S]
        if len(pts) < 5 or pts[-1, 0] - pts[0, 0] < 4:
            return
        fit = np.polyfit(pts[:, 0], pts[:, 1], 1)
        low = pts[pts[:, 1] - np.polyval(fit, pts[:, 0]) <= 0.02]   # lower envelope
        self.line = np.polyfit(low[:, 0], low[:, 1], 1) if len(low) >= 4 else fit
        self.r = float(np.clip(self.line[0], -0.1, 0.1))

class Manager:
    def __init__(self, send, log, say, enabled, cmd=None, failsafe=False):
        self.send, self.log, self.say, self.on = send, log, say, enabled
        self.p, self.mtime, self.shed, self.hi, self.lo, self.verify, self.ids = None, None, 0, None, None, None, []
        self.cmd, self.fs_on, self.fs, self.fs_q, self.armed = cmd, failsafe, False, [], None
        self.fs_stale = self.fs_bo = self.fresh_t = None
    def guard(self, now, pa, link, heard):
        """Downlink-aware failsafe (bay demo). PX4's own datalink failsafe watches the GCS heartbeat on the UPLINK,
        which still gets through; this watches what the operator actually RECEIVES. Latch-once RTL when
        (every sheddable tier is shed AND picture_age > STALE_S for FS_STALE_T) OR (link blackout for FS_BO_T)."""
        self.fresh_t = (self.fresh_t or now) if pa is not None and pa < FS_FRESH_S else None
        if not (self.on and self.fs_on and self.cmd) or self.fs or not heard or self.armed is False:
            self.fs_stale = self.fs_bo = None             # off, latched, never heard PX4, or known disarmed
            return
        stale = bool(self.ids) and self.shed >= len(self.ids) - 1 and pa is not None and pa > STALE_S
        self.fs_stale = (self.fs_stale or now) if stale else None
        self.fs_bo = (self.fs_bo or now) if link == "blackout" else None
        reason = (f"all {self.shed} sheddable tiers shed and picture_age>{STALE_S:g}s for {FS_STALE_T:g}s"
                  if self.fs_stale and now - self.fs_stale >= FS_STALE_T else
                  f"downlink blackout for {FS_BO_T:g}s" if self.fs_bo and now - self.fs_bo >= FS_BO_T else None)
        if reason:
            self.fs, self.fs_q = True, [now + FS_GAP_S * i for i in range(FS_SENDS)]
            self.log({"t": now, "kind": "event", "what": "failsafe", "action": "RTL", "reason": reason,
                      "picture_age_s": None if pa is None else round(pa, 3), "link": link, "tier": self.shed})
            self.say(2, "TETHER: picture lost over water - RTL" if self.fs_stale else "TETHER: downlink lost - RTL")
            self.pump(now)
    def pump(self, now):                                 # the 3 RTL sends, FS_GAP_S apart, never blocking on ACK
        while self.fs_q and now >= self.fs_q[0]:
            self.fs_q.pop(0)
            self.cmd(MAV_CMD_NAV_RETURN_TO_LAUNCH)
            self.log({"t": now, "kind": "event", "what": "cmd", "command": MAV_CMD_NAV_RETURN_TO_LAUNCH, "name": "RTL"})
    def fs_reset(self, now, why):
        if self.fs:
            self.log({"t": now, "kind": "event", "what": "failsafe_reset", "reason": why})
            self.say(6, "TETHER: failsafe re-armed")
        self.fs, self.fs_q, self.fs_stale, self.fs_bo = False, [], None, None
    def load(self, now):
        if not POLICY_PATH.exists():
            POLICY_PATH.write_text(json.dumps(default_policy(), indent=1) + "\n")
        if (mt := POLICY_PATH.stat().st_mtime) == self.mtime:
            return
        self.mtime = mt
        try:
            errs = validate_policy(p := json.loads(POLICY_PATH.read_text()))
        except ValueError as e:
            p, errs = None, [f"bad json: {e}"]
        if errs:
            self.log({"t": now, "kind": "event", "what": "policy_invalid", "errors": errs})
            print(f"policy.json rejected, keeping {self.p and self.p.get('name')}: {errs}", flush=True)
            self.p = self.p or default_policy()
        else:
            if self.p and self.shed:
                self.apply(now, 0, "policy reload", None)
            self.p = p
            self.log({"t": now, "kind": "event", "what": "policy", "name": p.get("name"), "tiers": p["tiers"]})
        self.ids = [{MSG_IDS[n]: n for n in t} for t in self.p["tiers"]]
    def tier_of(self, msgid):
        return next((k for k, t in enumerate(self.ids) if msgid in t), None)
    def cmds(self, now, ks, iv, quiet=False):
        for k in ks:
            for mid, name in self.ids[k].items():
                self.send(mid, iv)
                quiet or self.log({"t": now, "kind": "event", "what": "cmd511", "msg": name, "msgid": mid,
                                   "interval_us": iv})
    def apply(self, now, new, reason, rx):
        n, old = len(self.ids), self.shed
        ks, iv = (range(n - new, n - old), -1) if new > old else (range(n - old, n - new), 0)
        self.log({"t": now, "kind": "event", "what": "shed" if iv < 0 else "restore", "tier": new, "reason": reason})
        self.cmds(now, ks, iv)
        self.say(*((4, f"TETHER: link degraded - shed {new} tiers, {sum(len(self.ids[k]) for k in ks)} streams")
                   if iv < 0 else (6, f"TETHER: link recovered - restored tier {ks[0]}") if len(ks) == 1 else
                   (6, f"TETHER: {reason} - all streams restored")))
        self.shed, self.hi, self.lo = new, None, None
        self.verify = (now + 1.0, list(ks), iv, list(rx)) if rx else None
    def restore_all(self, now, reason):                  # every stream back to PX4 default, shed or not
        self.apply(now, 0, reason, None)
        self.cmds(now, range(1, len(self.ids)), 0)
    def toggle(self, now, on):
        if on != self.on:
            self.log({"t": now, "kind": "event", "what": "manager", "on": on})
            if self.fs and self.fresh_t is not None and now - self.fresh_t >= FS_RESET_FRESH_T:
                self.fs_reset(now, f"picture fresh (<{FS_FRESH_S:g}s) for {FS_RESET_FRESH_T:g}s + manager toggled")
            if not on:
                self.restore_all(now, "manager off")
            self.on, self.hi, self.lo, self.verify = on, None, None, None
    def step(self, now, qd, qd_t, rx):
        self.pump(now)                                   # pending RTL sends go out even if toggled off meanwhile
        if not self.on:
            return
        p, n = self.p, len(self.ids)
        if qd is None or now - qd_t > 1.0:               # no fresh critical frame: no evidence either way
            self.hi = self.lo = None
        else:
            self.hi = (self.hi or now) if qd > p["q_hi_s"] else None
            self.lo = (self.lo or now) if qd < p["q_lo_s"] else None
        if self.verify and now >= self.verify[0]:        # never wait for COMMAND_ACK: confirm by measured rate
            _, ks, iv, before = self.verify
            self.verify = None
            same = [k for k in ks if ((before[k] > 0 and rx[k] >= 0.5 * before[k]) if iv < 0
                                      else rx[k] <= before[k] + 0.5)]
            if same:
                self.log({"t": now, "kind": "event", "what": "resend", "tiers": same, "interval_us": iv,
                          "rx_hz": {f"T{k}": rx[k] for k in same}})
                self.cmds(now, same, iv)
        if self.hi is not None and now - self.hi >= p["T_detect_s"] and self.shed < n - 1:
            self.apply(now, n - 1, f"qdelay>{p['q_hi_s']}s for {p['T_detect_s']}s", rx)
        elif self.lo is not None and now - self.lo >= p["T_restore_s"] and self.shed > 0:
            self.apply(now, self.shed - 1, f"qdelay<{p['q_lo_s']}s for {p['T_restore_s']}s, probe up", rx)

def udp(addr):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(addr); s.setblocking(False)  # noqa: E702
    return s

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--udp-bind", type=int, default=tnet.DB_UDP_PORT, help="radio = UDP on 0.0.0.0:PORT")
    src.add_argument("--serial", help="radio = serial device (board 3, 115200, ESP32 held in reset)")
    ap.add_argument("--log", type=Path, default=ROOT / tnet.LIVE_DIR / "ground.jsonl")
    ap.add_argument("--manager", action="store_true", help="TETHER manager on at start (policy.json, cmd 511)")
    ap.add_argument("--mirror", help="also send the QGC stream to HOST[:14550] — a 2nd ground station (e.g. teammate)")
    ap.add_argument("--uplink", default=f"{tnet.LOCAL}:{tnet.AIR_UPLINK_PORT}",
                    help="command link HOST[:PORT] (QGC replies, cmd 511, RTL) — air.py's 14598; another laptop's IP "
                         "in a two-laptop split")
    ap.add_argument("--failsafe", action="store_true",
                    help="downlink-aware RTL failsafe (acts only while the manager is on; ctl {\"failsafe\": bool})")
    a = ap.parse_args()
    a.log.parent.mkdir(parents=True, exist_ok=True)
    logf = open(a.log, "w", buffering=1)
    log = lambda rec: (logf.write(json.dumps(rec) + "\n"), logf.flush())  # noqa: E731
    loc = socket.gethostbyname(tnet.LOCAL)
    uh, _, upp = a.uplink.partition(":")
    up_addr = (socket.gethostbyname(uh), int(upp or tnet.AIR_UPLINK_PORT))
    qgc_addr = (loc, tnet.QGC_PORT)
    gcs, ctl, ser, rsock = udp((loc, 0)), udp((loc, tnet.GROUND_CTRL_PORT)), None, None
    ups = gcs if up_addr[0].startswith("127.") else udp(("", 0))   # non-loopback uplink: wildcard-bound socket
    msock = maddr = None
    if a.mirror:
        mh, _, mp = a.mirror.partition(":")
        maddr, msock = (mh, int(mp or 14550)), udp(("", 0))
    if a.serial:
        import serial
        ser = serial.Serial()
        ser.port, ser.baudrate, ser.timeout = a.serial, 115200, 0
        ser.dtr, ser.rts = False, True                   # set before open(): holds the ESP32 adapter board in reset
        ser.open(); ser.rts = False; time.sleep(0.1); ser.rts = True  # noqa: E702  pulse, then hold
    else:
        rsock = udp(("", a.udp_bind))
    enc, veh = mav2.MAVLink(None, srcSystem=255, srcComponent=190), mav2.MAVLink(None, srcSystem=1, srcComponent=191)
    t_start = time.time()
    def send511(msgid, iv):
        ups.sendto(mav2.MAVLink_command_long_message(1, 1, 511, 0, msgid, iv, 0, 0, 0, 0, 0).pack(enc), up_addr)
    def send_cmd(command, *params):                      # COMMAND_LONG to PX4 1/1 over the command link
        p = (list(params) + [0.0] * 7)[:7]
        ups.sendto(mav2.MAVLink_command_long_message(1, 1, command, 0, *p).pack(enc), up_addr)
    def to_qgc(data):
        with suppress(OSError):
            gcs.sendto(data, qgc_addr)
        if msock is not None:
            with suppress(OSError):
                msock.sendto(data, maddr)
    def say(sev, text):                                  # TETHER -> operator, as a vehicle message in QGC
        print(text, flush=True)
        to_qgc(mav2.MAVLink_statustext_message(sev, text.encode()[:50]).pack(veh))
    def nvf(name, value):
        to_qgc(mav2.MAVLink_named_value_float_message(int((time.time() - t_start) * 1000), name.encode(),
                                                      value).pack(veh))

    now = time.time()
    mgr, clk, parser = Manager(send511, log, say, a.manager, send_cmd, a.failsafe), Clock(now), mav2.MAVLink(None)
    parser.robust_parsing = True                         # real RF: noise + BAD_DATA between valid frames
    mgr.load(now)
    win, last_seq, aoi_gen, pa = deque(), {}, {}, None   # win: (t, bytes, tier, gaps) per valid frame, last 1 s
    qd = qd_t = last_rx = None
    resets, next_reset = 2, now                          # start clean (either arm) even if a previous run died shed
    next_tick, next_status, next_policy, next_nvf = now, now + 1, now + 1, now + 0.5
    print(f"ground.py: radio {'serial ' + a.serial if a.serial else f'udp 0.0.0.0:{a.udp_bind}'} -> QGC "
          f"{tnet.LOCAL}:{tnet.QGC_PORT}; uplink -> :{tnet.AIR_UPLINK_PORT}; control :{tnet.GROUND_CTRL_PORT}; "
          f"manager {'ON' if a.manager else 'off'} (policy {mgr.p.get('name')}); failsafe "
          f"{'armed' if a.failsafe else 'off'}; log {a.log}", flush=True)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    try:
        while True:
            r, _, _ = select.select([ser.fileno() if ser else rsock, gcs, ctl] + ([msock] if msock else []), [], [],
                                    max(0.0, min(next_tick - time.time(), 0.05)))
            for f in r:
                if msock is not None and f is msock:          # 2nd ground station's commands -> PX4
                    with suppress(OSError):
                        ups.sendto(msock.recv(65535), up_addr)
                    continue
                if f is ctl:
                    with suppress(OSError, ValueError):
                        msg = json.loads(ctl.recv(65535))
                        if isinstance(msg, dict) and isinstance(msg.get("manager"), bool):
                            mgr.toggle(time.time(), msg["manager"])
                        if isinstance(msg, dict) and isinstance(msg.get("failsafe"), bool):
                            mgr.fs_on = msg["failsafe"]
                            log({"t": time.time(), "kind": "event", "what": "failsafe_enable", "on": mgr.fs_on})
                        if isinstance(msg, dict) and msg.get("failsafe_reset") is True:
                            mgr.fs_reset(time.time(), "ctl failsafe_reset")
                    continue
                if f is gcs:
                    with suppress(OSError):
                        ups.sendto(gcs.recv(65535), up_addr)     # QGC -> PX4 via air.py's command link
                    continue
                data = ser.read(ser.in_waiting or 1) if ser else rsock.recv(65535)
                if not data: continue  # noqa: E701
                to_qgc(data)
                t = time.time()
                for m in parser.parse_buffer(data) or []:
                    buf = m.get_msgbuf()                 # decoded frame bytes: goodput never counts raw noise
                    if m.get_type() == "BAD_DATA" or not buf or buf[0] not in (0xFD, 0xFE):
                        continue
                    seq, sysid, compid, msgid = frame_header(buf)
                    key = (sysid, compid)
                    if compid == DB_COMPID or last_seq.get(key) == seq:
                        continue                         # DroneBridge's own frames / exact duplicate
                    gaps = (seq - last_seq[key] - 1) & 0xFF if key in last_seq else 0
                    gaps = gaps if gaps < 128 else 0     # big jump = reorder/restart, not loss
                    last_seq[key], last_rx, tier = seq, t, mgr.tier_of(msgid)
                    win.append((t, len(buf), tier, gaps))
                    tbm = getattr(m, "time_boot_ms", None)
                    mt = m.get_type()
                    if mt == "HEARTBEAT" and sysid == 1 and compid == 1:
                        mgr.armed = bool(m.base_mode & 128)      # failsafe never fires at a disarmed vehicle
                    elif mt == "COMMAND_ACK" and m.command == MAV_CMD_NAV_RETURN_TO_LAUNCH:
                        log({"t": t, "kind": "event", "what": "ack", "command": m.command, "result": m.result})
                    if tier == 0 and tbm is not None:
                        qd, qd_t, aoi_gen[m.get_type()] = clk.add(m.get_type(), t, tbm / 1000.0), t, tbm / 1000.0
            now = time.time()
            while win and win[0][0] < now - 1.0: win.popleft()  # noqa: E701
            rx = [sum(1 for w in win if w[2] == k) for k in range(len(mgr.ids))]
            mgr.step(now, qd, qd_t, rx)
            if resets and last_rx is not None and now >= next_reset:   # PX4 talks, so air.py forwards: send twice
                log({"t": now, "kind": "event", "what": "reset", "reason": "start: all streams to PX4 default"})
                mgr.cmds(now, range(1, len(mgr.ids)), 0, quiet=True)
                resets, next_reset = resets - 1, now + 1.0
            if now >= next_policy:                       # 1 Hz: policy mtime check + skew persisted for the next run
                next_policy = now + 1.0
                mgr.load(now)
                SKEW_PATH.write_text(json.dumps({"r": clk.r, "t": now}))
            if now >= next_nvf:
                next_nvf = now + 0.5
                pa is None or nvf("PIC_AGE", pa)
                nvf("TIER", float(mgr.shed))
            if now >= next_tick:
                next_tick = max(next_tick + 0.2, now - 0.1)
                aoi = {n: round(now - (g + clk.offset(n, now)), 3) for n, g in aoi_gen.items()}
                pa, n_rx, n_lost, gp = aoi.get("ATTITUDE"), len(win), sum(w[3] for w in win), sum(w[1] for w in win)
                loss = n_lost / (n_rx + n_lost) if n_rx + n_lost else 0.0
                link = "blackout" if last_rx is None or now - last_rx > BLACKOUT_S else \
                       "stale" if pa is None or pa > STALE_S else "ok"
                log({"t": round(now, 3), "kind": "tick", "picture_age_s": pa, "aoi_s": aoi,
                     "qdelay_s": None if qd is None else round(qd, 3), "loss": round(loss, 4), "goodput_Bps": gp,
                     "rx_hz": {f"T{k}": float(v) for k, v in enumerate(rx)}, "link": link, "tier": mgr.shed,
                     "manager": mgr.on, "skew": round(clk.r, 5), "failsafe": mgr.fs})
                mgr.guard(now, pa, link, last_rx is not None)
                if now >= next_status:
                    next_status = now + 1.0
                    f2 = lambda x: "—" if x is None else f"{x:.2f}"  # noqa: E731
                    print(f"{time.strftime('%H:%M:%S')} picture_age {f2(pa)} s  goodput {gp:5d} B/s  loss {100 * loss:4.1f}%"
                          f"  tier {mgr.shed}  link {link:<8} qdelay {f2(qd)}  skew {100 * clk.r:+.2f}%  mgr {'ON' if mgr.on else 'off'}"
                          f"{'  FAILSAFE RTL' if mgr.fs else ''}", flush=True)
    except KeyboardInterrupt: pass  # noqa: E701  (SIGINT from sweep.py, SIGTERM mapped above)
    finally:
        if mgr.on and mgr.ids:                           # restore every stream so the next run starts clean
            mgr.restore_all(time.time(), "exit")         # (lost if air.py dies first: the next start resets)
        with suppress(OSError):
            SKEW_PATH.write_text(json.dumps({"r": clk.r, "t": time.time()}))  # noqa: E701
        logf.close()
        print("ground.py: exit" + (" (streams restored)" if mgr.on else ""), flush=True)

if __name__ == "__main__":
    main()
