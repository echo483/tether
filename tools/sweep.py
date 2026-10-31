#!/usr/bin/env python3
"""sweep.py — interleaved paired sweep, ABAB: U0 (manager off) then M (TETHER on), one seed per pair.

    ~/.local/bin/uv run python tools/sweep.py                       # 10 pairs, ~60 s/pair; operator runs air/ground
    ~/.local/bin/uv run python tools/sweep.py --pairs 3 --c-lo 1600 # the sweep steps C itself via {"C_Bps": …}
    ~/.local/bin/uv run python tools/sweep.py --boundary-c 700      # + one M run stepped below L_crit
    ~/.local/bin/uv run python tools/sweep.py --launch              # start air.py/ground.py per arm (once they exist)
    ~/.local/bin/uv run python tools/sweep.py --dry-run             # print the plan; send, create, sleep nothing

Per arm: mkdir <logs>/<YYYYmmdd-HHMMSS-arm-seed>/, then on the arm clock: +0 {"C_Bps": null} and
{"profile": "step", "seed": N} (air.py's seeded, time-indexed step, so both arms of a pair see the same
C(t)) — or, with --c-lo, {"C_Bps": c_lo} at --t-on and {"C_Bps": null} at --t-off; {"blackout_s": S} at
--blackout-at if given; {"C_Bps": null} at --run-s. Control = one JSON line per UDP datagram to
tnet.LOCAL:tnet.AIR_CTRL_PORT (CONTRACT.md §4). A refused datagram (nobody on the port) fails the arm.
Finished arms are appended to <logs>/runs.csv (run_id, arm, seed, start, end, dir) for analyze.py + the demo.

Launch layer (pluggable: Manual | Procs). Default Manual: the operator runs air.py + ground.py by hand;
the sweep only drives the control port, times the arms and says whether the manager must be ON (--confirm
waits for Enter before each arm). --launch = Procs: runs --air-cmd / --ground-cmd per arm (env
TETHER_RUN_ID / _RUN_DIR / _ARM / _SEED / _MANAGER) and SIGINTs them at the end of the arm; if air.py or
ground.py is absent it says so and falls back to Manual (run dirs are created, nothing launched/recorded).
"""
import argparse, csv, json, os, shlex, signal, socket, subprocess, sys, time  # noqa: E401
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import tnet  # noqa: E402  — CONTRACT §1 port map; never retype ports or addresses

CSV_COLS = ["run_id", "arm", "seed", "start", "end", "dir"]
AIR_CMD = "{py} {air_py} --log {dir}/air.jsonl --seed {seed}"   # assumed CLIs: override when air/ground land
GROUND_CMD = "{py} {ground_py} --log {dir}/ground.jsonl{manager_flag}"


def find(name):
    return next((p for p in (ROOT / name, HERE / name) if p.exists()), ROOT / name)


class Ctl:
    """air.py control door. Connected UDP socket, so an ICMP port-unreachable surfaces as a refusal."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.connect((tnet.LOCAL, tnet.AIR_CTRL_PORT))
        self.sock.setblocking(False)

    def send(self, msg):
        try:
            self.sock.send((json.dumps(msg) + "\n").encode())
            time.sleep(0.02)
            self.sock.recv(4096)                       # normally nothing to read; raises if the port refused
        except BlockingIOError:
            pass
        except ConnectionRefusedError:
            return False
        return True


class Manual:
    """Default launcher: start nothing; tell the operator which arm is next."""

    def __init__(self, confirm=False):
        self.confirm = confirm

    def start(self, run):
        msg = f"    operator: manager {'ON' if run['arm'] == 'M' else 'OFF'} for {run['run_id']}"
        input(msg + " — Enter to start ") if self.confirm else print(msg, flush=True)

    def alive(self):
        return True

    def stop(self):
        pass


class Procs:
    """--launch: air.py + ground.py per arm from command templates, stdout -> <run_dir>/<proc>.out."""

    def __init__(self, a):
        self.a, self.procs = a, []

    def start(self, run):
        d, m = run["dir"], run["arm"] == "M"
        env = dict(os.environ, TETHER_RUN_ID=run["run_id"], TETHER_RUN_DIR=str(d), TETHER_ARM=run["arm"],
                   TETHER_SEED=str(run["seed"]), TETHER_MANAGER=str(int(m)))
        fmt = dict(py=sys.executable, air_py=self.a.air_py, ground_py=self.a.ground_py, dir=d, seed=run["seed"],
                   run_id=run["run_id"], arm=run["arm"], manager_flag=" --manager" if m else "")
        for name, tpl in (("air", self.a.air_cmd), ("ground", self.a.ground_cmd)):
            with open(d / f"{name}.out", "w") as out:
                self.procs.append(subprocess.Popen(shlex.split(tpl.format(**fmt)), cwd=ROOT, env=env,
                                                   stdout=out, stderr=subprocess.STDOUT))
        time.sleep(self.a.warmup_s)

    def alive(self):
        return all(p.poll() is None for p in self.procs)

    def stop(self):
        for p in self.procs:
            if p.poll() is None:
                p.send_signal(signal.SIGINT)           # lets the manager restore streams and flush its log
        for p in self.procs:
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        self.procs = []


def schedule(a, seed, c_lo):
    """[(seconds into the arm, control message)] — time-indexed, identical for both arms of a pair."""
    num = lambda x: int(x) if float(x).is_integer() else x  # noqa: E731  {"C_Bps": 4000}, as in CONTRACT §4
    ev = [(0.0, {"C_Bps": None})]
    ev += [(0.0, {"profile": "step", "seed": seed})] if c_lo is None else \
          [(a.t_on, {"C_Bps": num(c_lo)}), (a.t_off, {"C_Bps": None})]
    if a.blackout_at is not None:
        ev.append((a.blackout_at, {"blackout_s": num(a.blackout_s)}))
    return sorted(ev, key=lambda e: e[0]) + [(a.run_s, {"C_Bps": None})]


def logline(run):
    """(one-liner text, logs present?) from analyze.measure — never allowed to kill the sweep."""
    try:
        import analyze
        m = analyze.measure(run)
    except Exception as e:  # noqa: BLE001
        return f"logs unreadable: {e}", False
    if m is None:
        return "no ground.jsonl ticks in the run dir", False
    warn = "  WARN streams still shed at the end → the next U0 arm is contaminated" if m["tier_end"] else ""
    c = f"{m['C']:.0f}" if m["C"] else "—"
    return (f"stale {100 * m['stale']:.0f}%  p50 {m['p50']:.2f}s  p99 {m['p99']:.2f}s  C {c}  "
            f"tier_end {m['tier_end']}{warn}"), True


def run_arm(a, ctl, launcher, arm, seed, c_lo, label):
    while (a.logs / (run_id := f"{time.strftime('%Y%m%d-%H%M%S')}-{arm}-{seed}")).exists():
        time.sleep(0.2)                                # run_id has 1 s resolution
    run = {"run_id": run_id, "arm": arm, "seed": seed, "dir": a.logs / run_id}
    run["dir"].mkdir(parents=True)
    launcher.start(run)
    t0, why = time.time(), ""
    for at, msg in schedule(a, seed, c_lo):
        while time.time() < t0 + at and launcher.alive():
            time.sleep(min(0.25, max(0.0, t0 + at - time.time())))
        if not launcher.alive():
            why = "air.py/ground.py exited early"
            break
        if not ctl.send(msg):
            why = f"control refused at +{at:g}s — nothing on {tnet.LOCAL}:{tnet.AIR_CTRL_PORT} (air.py up?)"
            break
    end = time.time()
    launcher.stop()
    run.update(start=t0, end=end)
    if not why:
        new = not (a.logs / "runs.csv").exists()
        with open(a.logs / "runs.csv", "a", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            if new:
                w.writerow(CSV_COLS)
            w.writerow([run_id, arm, seed, f"{t0:.3f}", f"{end:.3f}", os.path.relpath(run["dir"], ROOT)])
    text, has_logs = logline(run)
    print(f"  {label:<14} {run_id:<26} {'ok ' if not why else 'BAD'} {end - t0:5.1f}s  "
          + (f"✗ {why}" if why else text), flush=True)
    return not why, has_logs


def main():
    ap = argparse.ArgumentParser(description="TETHER interleaved paired sweep (see the module docstring)")
    ap.add_argument("--pairs", type=int, default=10)
    ap.add_argument("--seed0", type=int, default=1, help="pair i uses seed seed0+i in both arms")
    ap.add_argument("--run-s", type=float, default=28.0, help="arm length; a pair = 2 × (run_s + gap_s) ≈ 60 s")
    ap.add_argument("--gap-s", type=float, default=2.0, help="settle between arms (queue drains, streams restore)")
    ap.add_argument("--c-lo", type=float, help="step C here (C_Bps over [t_on, t_off)) instead of air.py's profile")
    ap.add_argument("--t-on", type=float, default=5.0)
    ap.add_argument("--t-off", type=float, default=23.0)
    ap.add_argument("--blackout-at", type=float, help="send {'blackout_s': S} this many seconds into every arm")
    ap.add_argument("--blackout-s", type=float, default=3.0)
    ap.add_argument("--boundary-c", type=float, help="after the pairs, one M run stepped to this C (< L_crit)")
    ap.add_argument("--logs", type=Path, default=ROOT / "logs")
    ap.add_argument("--launch", action="store_true", help="start air.py/ground.py per arm (default: operator does)")
    ap.add_argument("--air-py", type=Path, default=find("air.py"))
    ap.add_argument("--ground-py", type=Path, default=find("ground.py"))
    ap.add_argument("--air-cmd", default=AIR_CMD, help=f"template, default {AIR_CMD!r}")
    ap.add_argument("--ground-cmd", default=GROUND_CMD, help=f"template, default {GROUND_CMD!r}")
    ap.add_argument("--warmup-s", type=float, default=3.0, help="--launch: wait after starting the processes")
    ap.add_argument("--confirm", action="store_true", help="manual mode: wait for Enter before each arm")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and messages, then exit")
    a = ap.parse_args()
    plan = [(arm, a.seed0 + i, a.c_lo, f"[pair {i + 1}/{a.pairs}]") for i in range(a.pairs) for arm in ("U0", "M")]
    plan += [("M", a.seed0 + a.pairs, a.boundary_c, "[boundary]")] if a.boundary_c else []
    if a.dry_run:
        for arm, seed, c, label in plan:
            print(f"  {label:<14} {arm:<2} seed {seed}: " + " · ".join(f"+{t:g}s {json.dumps(m)}"
                                                                       for t, m in schedule(a, seed, c)))
        return 0
    launcher = Manual(a.confirm)
    if a.launch:
        missing = [str(p) for p in (a.air_py, a.ground_py) if not p.exists()]
        if missing:
            print(f"--launch: {', '.join(missing)} absent → manual mode (run dirs only; nothing launched or recorded)")
        else:
            launcher = Procs(a)
    pair_s = 2 * (a.run_s + a.gap_s + (a.warmup_s if isinstance(launcher, Procs) else 0))
    print(f"sweep: {a.pairs} pairs ABAB (U0 then M, same seed), ~{pair_s:.0f} s/pair, "
          f"{'C_Bps ' + format(a.c_lo, 'g') if a.c_lo else 'profile step'} · launcher {type(launcher).__name__} · "
          f"control → {tnet.LOCAL}:{tnet.AIR_CTRL_PORT} · logs → {os.path.relpath(a.logs, ROOT)}/", flush=True)
    ctl, res = Ctl(), {}
    try:
        for arm, seed, c, label in plan:
            res.setdefault(label, []).append(run_arm(a, ctl, launcher, arm, seed, c, label))
            time.sleep(a.gap_s)
    except KeyboardInterrupt:
        print("\ninterrupted — stopping processes, C back to unlimited")
        launcher.stop()
        ctl.send({"C_Bps": None})
    done = sum(len(v) == 2 and all(ok for ok, _ in v) for k, v in res.items() if k.startswith("[pair"))
    runs = [r for v in res.values() for r in v]
    bnd = f" · boundary run {'ok' if res['[boundary]'][0][0] else 'FAILED'}" if "[boundary]" in res else ""
    print(f"SWEEP {'PASS' if done == a.pairs else 'FAIL'}: {done}/{a.pairs} pairs completed · logs present for "
          f"{sum(h for _, h in runs)}/{len(runs)} runs{bnd} · {os.path.relpath(a.logs / 'runs.csv', ROOT)}")
    print(f"next: ~/.local/bin/uv run python tools/analyze.py {os.path.relpath(a.logs / 'runs.csv', ROOT)}")
    return 0 if done == a.pairs else 1


if __name__ == "__main__":
    sys.exit(main())
