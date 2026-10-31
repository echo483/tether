#!/usr/bin/env python3
"""air.py — TETHER air-side shuttle: PX4 UDP <-> radio, bounded drop-tail downlink queue, seeded squeeze.

    ~/.local/bin/uv run python tools/air.py --emulated                      # radio = UDP to localhost:14550
    ~/.local/bin/uv run python tools/air.py --dev /dev/serial/by-path/<…>   # radio = board-3 UART @ 115200

Downlink only is squeezed (CONTRACT §5): each PX4 datagram enters a drop-tail byte queue capped at K (one that
does not fit is dropped whole, counted), drained by a token bucket at C B/s (None = line rate baud/10), depth =
one max datagram. Real mode: non-blocking serial writes, only while the kernel tty out-queue < --kernel-max.
Emulated: one UDP datagram per PX4 datagram, localhost:EMU_SRC_PORT -> tnet.LOCAL:tnet.DB_UDP_PORT (as
DroneBridge pushes). Uplink (serial bytes / datagrams back on the emulated socket) goes unparsed to PX4's
learned source address from the SAME socket (per-instance cmd 511).
Control, tnet.LOCAL:tnet.AIR_CTRL_PORT udp, one JSON object per datagram (or line), keys combinable (§4):
  {"C_Bps": 1600} · {"C_Bps": null}  set C / unlimited; cancels a running profile
  {"profile": "step", "seed": N}     from now: unlimited 10 s, --c-lo until 40 s, then unlimited (time-indexed,
                                     deterministic; seed recorded; optional "c_lo"/"t_on"/"t_off" keys)
  {"blackout_s": S}                  drop ALL downlink arrivals for S s, queue frozen (logged as C_Bps 0)
  {"K_bytes": n}                     set K
  {"range_model": true|false}        bay demo: C from the vehicle's distance to home (overrides C/profile while on)
Range model (--range-model): air.py parses PX4's own downlink BEFORE the queue (ground truth, never the squeezed
copy) for GLOBAL_POSITION_INT + HOME_POSITION (fallback home = first fix); d = equirectangular distance to home;
d < --r-near -> unlimited · < --r-mid -> --c-mid B/s · < --r-far -> --c-far B/s · beyond -> blackout (drop all).
Log: 1 Hz kind "air" lines (§2) + one kind "ctl" line per message -> --log | $TETHER_RUN_DIR/air.jsonl |
logs/air-<ts>/air.jsonl. sweep.py --launch passes `--log … --seed N` only: put --emulated/--dev in --air-cmd
or export TETHER_EMULATED=1 / TETHER_DEV=<path>.
"""
import argparse, collections, errno, json, math, os, select, signal, socket, sys, time  # noqa: E401
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tnet  # noqa: E402  — CONTRACT §1 port map

EMU_SRC_PORT = tnet.DB_UDP_PORT + 1          # emulated DroneBridge's own port; ground.py's uplink lands here
env_seed = os.environ.get("TETHER_SEED")
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--emulated", action="store_true", default=os.environ.get("TETHER_EMULATED") == "1")
ap.add_argument("--dev", default=os.environ.get("TETHER_DEV"), help="serial device (real mode)")
ap.add_argument("--baud", type=int, default=115200)
ap.add_argument("--k-bytes", type=int, default=3200, help="downlink queue cap K (bytes)")
ap.add_argument("--c-bps", type=float, default=None, help="initial C (default unlimited = line rate)")
ap.add_argument("--c-lo", type=float, default=1600.0, help="C during the step profile's squeeze")
ap.add_argument("--seed", type=int, default=int(env_seed) if env_seed else None)
ap.add_argument("--log", type=Path, help="air.jsonl path (default $TETHER_RUN_DIR/air.jsonl)")
ap.add_argument("--kernel-max", type=int, default=256, help="real mode: max bytes in the kernel tty out-queue")
ap.add_argument("--hold-reset", action=argparse.BooleanOptionalAction, default=True)
ap.add_argument("--emu-port", type=int, default=EMU_SRC_PORT, help="emulated mode: our source port")
ap.add_argument("--radio-host", default=os.environ.get("TETHER_RADIO_HOST"),
                help="real RF: UDP to this host:14550 (board 1 = 192.168.2.1), same pacing as --emulated")
ap.add_argument("--range-model", action="store_true", help="capacity from distance to home (bay demo); ctl toggles")
ap.add_argument("--r-near", type=float, default=250.0, help="range model: unlimited below this (m)")
ap.add_argument("--r-mid", type=float, default=550.0, help="range model: --c-mid below this (m)")
ap.add_argument("--r-far", type=float, default=800.0, help="range model: --c-far below this, blackout beyond (m)")
ap.add_argument("--c-mid", type=float, default=1600.0, help="range model: C between --r-near and --r-mid (B/s)")
ap.add_argument("--c-far", type=float, default=700.0, help="range model: C between --r-mid and --r-far (B/s)")
a = ap.parse_args()
if not a.emulated and not a.dev and not a.radio_host:
    ap.error("pick the radio side: --emulated, --radio-host HOST, or --dev PATH")
UDP_RADIO = a.emulated or bool(a.radio_host)       # emulated == radio-host localhost
live = not a.log and not os.environ.get("TETHER_RUN_DIR")
log_path = a.log or (Path(os.environ["TETHER_RUN_DIR"]) / "air.jsonl" if os.environ.get("TETHER_RUN_DIR")
                     else HERE.parent / tnet.LIVE_DIR / "air.jsonl")
log_path.parent.mkdir(parents=True, exist_ok=True)
logf = open(log_path, "w" if live else "a", buffering=1)


def udp(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind((tnet.LOCAL, port)); s.setblocking(False)  # noqa
    return s


px4s, ctl, upl = udp(tnet.PX4_PORT), udp(tnet.AIR_CTRL_PORT), udp(tnet.AIR_UPLINK_PORT)
if a.radio_host and a.radio_host not in ("localhost", tnet.LOCAL) and not a.radio_host.startswith("127."):
    upl.close()                              # two-laptop split: laptop 2's ground.py --uplink reaches us over WiFi
    upl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); upl.bind(("", tnet.AIR_UPLINK_PORT)); upl.setblocking(False)  # noqa
ser = emu = fd = None
if UDP_RADIO:
    if a.radio_host and a.radio_host not in ("localhost", tnet.LOCAL):
        emu = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); emu.bind(("", a.emu_port)); emu.setblocking(False)  # noqa
    else:
        emu = udp(a.emu_port)
    ground = socket.getaddrinfo(a.radio_host or tnet.LOCAL, tnet.DB_UDP_PORT, socket.AF_INET, socket.SOCK_DGRAM)[0][4]
else:                                        # mirrors shuttle_passthrough.py + loopback3.py's tested open
    import serial
    ser = serial.Serial()                    # unopened: set lines first so EN is held low from the moment we open
    ser.port, ser.baudrate, ser.timeout = a.dev, a.baud, 0
    if a.hold_reset:
        ser.dtr, ser.rts = False, True
    ser.open()
    if a.hold_reset:                         # explicit reset pulse, then hold
        ser.rts = False; time.sleep(0.1); ser.rts = True; time.sleep(0.4); ser.reset_input_buffer()  # noqa: E702
    fd = ser.fileno()                        # pyserial opens O_NONBLOCK on POSIX; we os.write() it ourselves
rfds = [px4s, ctl, upl, emu if UDP_RADIO else fd]
LINE = a.baud / 10.0                         # 8N1 line rate, B/s
S = dict(C=a.c_bps, K=a.k_bytes, seed=a.seed, prof=None, bo_until=0.0, px4=None,
         rm=a.range_model, home=None, home_src=None, pos=None, rng=None, alt=None)
q, qb, inflight = collections.deque(), 0, b""
from pymavlink.dialects.v20 import common as _mav2  # noqa: E402  range model only reads, never re-encodes
MP = _mav2.MAVLink(None)
MP.robust_parsing = True                     # unknown/garbled frames become BAD_DATA, never an exception


def track(d):
    """Range model input: PX4's position + home from the raw downlink datagram (pre-queue = truth)."""
    try:
        msgs = MP.parse_buffer(d) or []
    except Exception:                        # never let a parse problem touch the shuttle
        return
    for m in msgs:
        t = m.get_type()
        if t == "GLOBAL_POSITION_INT" and (m.lat or m.lon):
            S["pos"], S["alt"] = (m.lat / 1e7, m.lon / 1e7), m.relative_alt / 1000.0
            if S["home"] is None:
                S["home"], S["home_src"] = S["pos"], "first_fix"
        elif t == "HOME_POSITION" and (m.latitude or m.longitude):
            S["home"], S["home_src"] = (m.latitude / 1e7, m.longitude / 1e7), "HOME_POSITION"
    if S["home"] and S["pos"]:               # equirectangular: plenty at < 2 km
        (la0, lo0), (la, lo) = S["home"], S["pos"]
        S["rng"] = 6371000.0 * math.hypot(math.radians(la - la0),
                                          math.radians(lo - lo0) * math.cos(math.radians((la + la0) / 2)))


def range_cap():
    """(C, blackout) from distance to home; no fix yet -> unlimited."""
    d = S["rng"]
    if d is None or d < a.r_near:
        return None, False
    return (a.c_mid, False) if d < a.r_mid else (a.c_far, False) if d < a.r_far else (0.0, True)
st, win = dict(drops=0, drops_bo=0, nopeer=0), dict(off=0, sent=0, up=0)


num = lambda x: None if x is None else int(x) if float(x).is_integer() else round(x, 1)  # noqa: E731


def out_waiting():
    try:
        return ser.out_waiting
    except (OSError, serial.SerialException):
        return 0


def cap(now):
    """Effective C at monotonic `now` (None = unlimited). The step profile is a pure function of time."""
    if S["rm"]:
        return range_cap()[0]
    p = S["prof"]
    if p:
        dt = now - p["t0"]
        if dt < p["t_off"]:
            return p["c_lo"] if dt >= p["t_on"] else None
        S["prof"], S["C"] = None, None       # profile over -> unlimited
    return S["C"]


def control(raw, now):
    for line in filter(str.strip, raw.decode(errors="replace").splitlines()):
        try:
            m = json.loads(line)
        except ValueError:
            m = None
        if not isinstance(m, dict):
            print(f"air: ctl ignored {line[:80]!r}", flush=True)
            continue
        if "C_Bps" in m:
            S["C"], S["prof"] = (None if m["C_Bps"] is None else max(0.0, float(m["C_Bps"]))), None
        if "K_bytes" in m:
            S["K"] = int(m["K_bytes"])
        if "seed" in m:
            S["seed"] = m["seed"]
        if m.get("profile") == "step":
            S["C"], S["prof"] = None, dict(t0=now, c_lo=float(m.get("c_lo", a.c_lo)),
                                           t_on=float(m.get("t_on", 10.0)), t_off=float(m.get("t_off", 40.0)))
        elif "profile" in m:
            print(f"air: unknown profile {m['profile']!r} ignored", flush=True)
        if "blackout_s" in m:
            S["bo_until"] = now + max(0.0, float(m["blackout_s"]))
        if isinstance(m.get("range_model"), bool):
            S["rm"] = m["range_model"]
        logf.write(json.dumps({"t": time.time(), "kind": "ctl", "msg": m}) + "\n")
        print(f"air: ctl {json.dumps(m)}", flush=True)


def to_px4(data):                            # uplink: untouched, unparsed
    if data and S["px4"]:
        px4s.sendto(data, S["px4"])
        win["up"] += len(data)
    elif data:
        st["nopeer"] += len(data)


signal.signal(signal.SIGTERM, signal.default_int_handler)   # SIGTERM == SIGINT: clean exit via finally
radio = f"udp :{a.emu_port} -> {ground[0]}:{ground[1]} ({'emulated' if a.emulated else 'REAL RF via board 1'})" if UDP_RADIO \
    else f"{a.dev} @{a.baud} hold_reset={a.hold_reset}"
print(f"air: px4 {tnet.LOCAL}:{tnet.PX4_PORT} <-> {radio} · ctl {tnet.LOCAL}:{tnet.AIR_CTRL_PORT} · "
      f"K={S['K']} B · log {log_path}", flush=True)
depth, tok = 300.0, 0.0
t_last = t_win = time.monotonic()
try:
    while True:
        r, _, _ = select.select(rfds, [], [], 0.005)
        now = time.monotonic()
        bo = now < S["bo_until"] or (S["rm"] and range_cap()[1])
        while px4s in r:                     # PX4 -> drop-tail queue (drain every pending datagram)
            try:
                d, src = px4s.recvfrom(65535)
            except BlockingIOError:
                break
            if S["px4"] != src:
                S["px4"] = src
                print(f"air: PX4 peer = {src}", flush=True)
            win["off"] += len(d)
            track(d)
            depth = max(depth, float(len(d)))
            if bo or qb + len(d) > S["K"]:
                st["drops"] += 1; st["drops_bo"] += bo  # noqa: E702
            else:
                q.append(d); qb += len(d)  # noqa: E702
        for s in (ctl, emu, upl):            # control door; radio uplink + command link (14598) -> PX4
            while s is not None and s in r:
                try:
                    d, _src = s.recvfrom(65535)
                except BlockingIOError:
                    break
                except OSError:
                    continue
                control(d, now) if s is ctl else to_px4(d)
        if fd is not None and fd in r:       # serial -> PX4
            to_px4(ser.read(4096))
        c = cap(now)
        tok, t_last = min(tok + (now - t_last) * (LINE if c is None else min(c, LINE)), depth), now
        if not bo and UDP_RADIO:
            while q and tok >= len(q[0]):
                d = q.popleft(); qb -= len(d); tok -= len(d); win["sent"] += len(d)  # noqa: E702
                try:
                    emu.sendto(d, ground)
                except OSError:
                    pass
        elif not bo and (inflight or q) and (budget := int(min(tok, a.kernel_max - out_waiting()))) > 0:
            if not inflight:
                inflight = q.popleft(); qb -= len(inflight)  # noqa: E702
            try:
                n = os.write(fd, inflight[:budget])
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
                    raise
                n = 0
            inflight, tok, win["sent"] = inflight[n:], tok - n, win["sent"] + n
        if now - t_win >= 1.0:
            el, t_win = now - t_win, now
            rec = {"t": time.time(), "kind": "air", "C_Bps": 0 if bo else num(c), "K_bytes": S["K"],
                   "offered_Bps": round(win["off"] / el), "sent_Bps": round(win["sent"] / el),
                   "q_bytes": qb + len(inflight), "drops": st["drops"], "seed": S["seed"], "emulated": a.emulated,
                   "blackout": bo, "C_set": num(c), "profile": "step" if S["prof"] else None,
                   "drops_bo": st["drops_bo"], "uplink_Bps": round(win["up"] / el),
                   "range_m": None if S["rng"] is None else round(S["rng"], 1), "range_model": S["rm"],
                   "alt_m": None if S["alt"] is None else round(S["alt"], 1), "home_src": S["home_src"]}
            logf.write(json.dumps(rec) + "\n")
            rng = "—" if S["rng"] is None else f"{S['rng']:.0f}"
            print(f"air C={'∞' if c is None else f'{c:.0f}'}{' BLACKOUT' if bo else ''} K={S['K']} "
                  f"off {rec['offered_Bps']} sent {rec['sent_Bps']} B/s q {rec['q_bytes']} B drops {st['drops']} "
                  f"(bo {st['drops_bo']}) up {rec['uplink_Bps']} B/s{' step' if S['prof'] and not S['rm'] else ''}"
                  f" range {rng} m{' [RANGE MODEL]' if S['rm'] else ''}", flush=True)
            win = dict(off=0, sent=0, up=0)
except KeyboardInterrupt:
    pass
finally:
    logf.close()
    if ser is not None:
        ser.close()
    print(f"air: exit · drops {st['drops']} · log {log_path}", flush=True)
