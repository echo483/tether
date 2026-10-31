#!/usr/bin/env python3
"""ground_selftest.py — ground.py self-test orchestrator (see notes/ground-selftest.md): air.py --emulated + ground.py + fake QGC listener on 14560."""
import json, os, signal, socket, subprocess, sys, time  # noqa: E401
from pathlib import Path

ROOT = Path.home() / "drone-labs/tether"
sys.path.insert(0, str(ROOT / "tools"))
from pymavlink.dialects.v20 import common as mav2  # noqa: E402

PY = [str(Path.home() / ".local/bin/uv"), "run", "python", "-u"]
mode = sys.argv[1]            # "basic" | "manager"   usage: ground_selftest.py MODE RUN_DIR [SECS] [JSON schedule]
run_dir = Path(sys.argv[2]); run_dir.mkdir(parents=True, exist_ok=True)
dur = float(sys.argv[3]) if len(sys.argv) > 3 else 20
subprocess.run(["pkill", "-f", "tools/air.py"]); time.sleep(0.5)
air = subprocess.Popen(PY + ["tools/air.py", "--emulated", "--log", str(run_dir / "air.jsonl")], cwd=ROOT,
                       stdout=open(run_dir / "air.out", "w"), stderr=subprocess.STDOUT)
qgc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); qgc.bind(("127.0.0.1", 14560)); qgc.settimeout(0.1)
time.sleep(2)
gargs = ["tools/ground.py", "--log", str(run_dir / "ground.jsonl")] + (["--manager"] if mode == "manager" else [])
gnd = subprocess.Popen(PY + gargs, cwd=ROOT, stdout=open(run_dir / "ground.out", "w"), stderr=subprocess.STDOUT)
ctl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sched = {"basic": [], "manager": [(10, {"C_Bps": 1600}), (40, {"C_Bps": None})]}[mode]
if len(sys.argv) > 4:
    sched = json.loads(sys.argv[4])
p = mav2.MAVLink(None); p.robust_parsing = True
t0, qbytes, texts, nvf, sent = time.time(), 0, [], {}, set()
start_air = t0
while time.time() - t0 < dur:
    for i, (at, msg) in enumerate(sched):
        if i not in sent and time.time() - t0 >= at:
            port = 14597 if "manager" in msg else 14599
            ctl.sendto(json.dumps(msg).encode(), ("127.0.0.1", port)); sent.add(i)
            print(f"+{time.time() - t0:5.1f}s sent {msg} -> {port}", flush=True)
    try:
        d = qgc.recv(65535)
    except socket.timeout:
        continue
    qbytes += len(d)
    for m in p.parse_buffer(d) or []:
        if m.get_type() == "STATUSTEXT":
            texts.append((round(time.time() - t0, 1), m.get_srcSystem(), m.get_srcComponent(), m.severity, m.text))
        elif m.get_type() == "NAMED_VALUE_FLOAT":
            nvf[m.name] = nvf.get(m.name, 0) + 1
gnd.send_signal(signal.SIGINT); gnd.wait(5)
time.sleep(1)
air.send_signal(signal.SIGINT)
try:
    air.wait(5)
except subprocess.TimeoutExpired:
    air.kill()
el = time.time() - t0
print(json.dumps({"qgc_bytes": qbytes, "qgc_Bps": round(qbytes / el, 1), "secs": round(el, 1),
                  "statustext": texts, "named_value_float_counts": nvf}, indent=1))
