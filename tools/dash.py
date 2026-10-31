"""dash.py — TETHER live dashboard (right half of the demo screen, next to QGC). Reads JSONL only.

    uv run python tools/dash.py                               # logs/live/{ground,air}.jsonl
    uv run python tools/dash.py --dir logs/<run_id>           # a sweep run dir (or logs/fake)
    uv run python tools/dash.py --dir logs/fake --snapshot notes/dash-snapshot.png --secs 25   # headless PNG

Files may be absent, truncated or restarted at any time: each is reopened when it shrinks or its inode changes.
"""
import argparse
import json
import os
import time
from collections import deque
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default="logs/live")
ap.add_argument("--snapshot", default=None, help="headless: run --secs then save this PNG and exit")
ap.add_argument("--secs", type=float, default=20.0)
ap.add_argument("--window", type=float, default=30.0, help="trace length, s")
a = ap.parse_args()

import matplotlib  # noqa: E402
if a.snapshot:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FuncAnimation  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
D = Path(a.dir) if Path(a.dir).is_absolute() or Path(a.dir).exists() else ROOT / a.dir
BG, FG, DIM = "#0b0e13", "#f2f5f8", "#7d8793"
GREEN, AMBER, RED, ORANGE, BLUE = "#21d07a", "#ffb020", "#ff4040", "#ff8c1a", "#3aa0ff"
LINK_COL = {"ok": GREEN, "stale": RED, "blackout": ORANGE}


class Tail:
    """Incremental JSONL reader that survives truncation/rotation and partial lines."""
    def __init__(s, path, maxlen):
        s.path, s.f, s.ino, s.buf = path, None, None, b""
        s.rows, s.events = deque(maxlen=maxlen), deque(maxlen=40)

    def poll(s):
        try:
            st = os.stat(s.path)
        except OSError:
            return
        if s.f is None or st.st_ino != s.ino or st.st_size < s.f.tell():
            if s.f:
                s.f.close()
            s.f, s.ino, s.buf = open(s.path, "rb"), st.st_ino, b""
            s.rows.clear(), s.events.clear()
        s.buf += s.f.read()
        *lines, s.buf = s.buf.split(b"\n")
        for ln in lines:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if isinstance(r, dict) and "t" in r:
                (s.events if r.get("kind") == "event" else s.rows).append(r)


ground, air = Tail(D / "ground.jsonl", 5 * 120), Tail(D / "air.jsonl", 120)
pol = {"mtime": None, "name": "default"}

plt.rcParams["toolbar"] = "None"                  # no matplotlib toolbar: every pixel is the dashboard
fig = plt.figure(figsize=(9.6, 10.2), facecolor=BG)
try:
    fig.canvas.manager.set_window_title("TETHER")
    if not a.snapshot:                              # right half of a 1920x1080 screen, QGC takes the left half
        fig.canvas.manager.window.wm_geometry("960x1020+960+0")
except Exception:
    pass
SC = {"s": 1.0}                                     # font scale follows the window size (resize-safe half screen)
top = fig.add_axes([0, 0.62, 1, 0.38]); top.axis("off")
tr = fig.add_axes([0.11, 0.28, 0.85, 0.31])
bot = fig.add_axes([0, 0, 1, 0.22]); bot.axis("off"); bot.set_xlim(0, 1); bot.set_ylim(0, 1)
top.text(0.5, 0.80, "PICTURE AGE", ha="center", va="center", fontsize=32, color=DIM, weight="bold")
num = top.text(0.5, 0.47, "—", ha="center", va="center", fontsize=118, weight="bold", family="monospace", color=DIM)
lnk = top.text(0.27, 0.10, "NO DATA", ha="center", va="center", fontsize=40, weight="bold", color=DIM)
mgr = top.text(0.73, 0.10, "", ha="center", va="center", fontsize=40, weight="bold", color=DIM)
emu = fig.text(0.985, 0.988, "EMULATED LINK", ha="right", va="top", fontsize=20, weight="bold", color=RED)
fig.text(0.015, 0.988, f"TETHER  ·  {D.name}", ha="left", va="top", fontsize=13, color=DIM)
boxes, blabels = [], []
for i, name in enumerate(("T0  critical", "T1", "T2  bulk")):
    r = Rectangle((0.05 + i * 0.31, 0.42), 0.28, 0.48, lw=4, ec=BLUE, fc=BLUE)
    bot.add_patch(r); boxes.append(r)
    blabels.append(bot.text(0.19 + i * 0.31, 0.66, name, ha="center", va="center", fontsize=24, weight="bold", color=FG))
stats = bot.text(0.5, 0.20, "", ha="center", va="center", fontsize=20, color=FG, family="monospace")
poltxt = bot.text(0.5, 0.03, "", ha="center", va="bottom", fontsize=14, color=DIM)
BASE = [(t, t.get_fontsize()) for t in fig.findobj(lambda o: hasattr(o, "set_fontsize") and hasattr(o, "get_text"))]


def on_resize(_ev=None):
    w, h = fig.get_size_inches() * fig.dpi
    SC["s"] = max(0.4, min(w / 960.0, h / 1020.0))
    for t, f0 in BASE:
        t.set_fontsize(f0 * SC["s"])


fig.canvas.mpl_connect("resize_event", on_resize)


def spans(rows, dur, pred):
    """Merge [t, t+dur) intervals of rows where pred(row) into a list of (t0, t1)."""
    out = []
    for r in rows:
        if pred(r):
            if out and r["t"] <= out[-1][1] + 0.05:
                out[-1][1] = r["t"] + dur
            else:
                out.append([r["t"], r["t"] + dur])
    return out


def c_of(r):  # configured C: air.py logs C_Bps 0 during a blackout, C_set keeps the squeeze value (None = unlimited)
    c = r.get("C_set", r.get("C_Bps"))
    return c if c else None


def age_color(v):
    return DIM if v is None else GREEN if v < 0.5 else AMBER if v <= 1.0 else RED


def update(_=None):
    ground.poll(), air.poll()
    try:
        m = os.stat(ROOT / "policy.json").st_mtime
        if m != pol["mtime"]:
            pol["mtime"], pol["name"] = m, json.load(open(ROOT / "policy.json")).get("name", "?")
    except (OSError, ValueError, AttributeError):
        pass
    now = time.time()
    ticks = list(ground.rows)
    last = ticks[-1] if ticks else None
    fresh = last is not None and now - last["t"] < 3.0
    anchor = now if fresh or last is None else last["t"]      # finished run dir: show its last window
    age = last.get("picture_age_s") if fresh else None
    num.set_text("—" if age is None else f"{age:.2f} s" if age < 10 else f"{age:.0f} s")
    num.set_color(age_color(age))
    link = (last.get("link") or "?") if fresh else "no data"
    lnk.set_text(link.upper()); lnk.set_color(LINK_COL.get(link, DIM))
    on = last.get("manager") if last else None
    fs = bool(last and last.get("failsafe"))
    mgr.set_text("" if on is None else "TETHER: RTL" if fs else "TETHER ON" if on else "TETHER OFF")
    mgr.set_color(DIM if not fresh else RED if fs else GREEN if on else AMBER)
    arows = [r for r in air.rows if r.get("kind", "air") == "air"]
    alast = arows[-1] if arows and anchor - arows[-1]["t"] < 5.0 else None
    emu.set_visible(alast is not None)
    if alast is not None:
        emu.set_text("EMULATED LINK" if alast.get("emulated") else "REAL 2.4 GHz LINK")
        emu.set_color(RED if alast.get("emulated") else GREEN)

    tr.cla(); tr.set_facecolor(BG)
    lo = anchor - a.window
    sq = spans(arows, 1.0, lambda r: c_of(r) is not None)
    for t0, t1 in sq:
        tr.axvspan(max(t0, lo) - anchor, min(t1, anchor) - anchor, color="#3b4a66", alpha=0.85, lw=0)
    bo = []
    for t0, t1 in sorted(spans(arows, 1.0, lambda r: r.get("blackout")) + spans(ticks, 0.2, lambda r: r.get("link") == "blackout")):
        if bo and t0 <= bo[-1][1]:
            bo[-1][1] = max(bo[-1][1], t1)
        else:
            bo.append([t0, t1])
    for t0, t1 in bo:
        tr.axvspan(max(t0, lo) - anchor, min(t1, anchor) - anchor, color=ORANGE, alpha=0.45, lw=0)
    win = [r for r in ticks if r["t"] >= lo]
    xs = [r["t"] - anchor for r in win]
    ys = [r["picture_age_s"] if r.get("picture_age_s") is not None else float("nan") for r in win]
    tr.plot(xs, ys, color=FG, lw=3)
    tr.axhline(1.0, color=RED, ls="--", lw=2)
    ymax = max([2.5] + [min(10.0, y * 1.15) for y in ys if y == y])
    tr.set_xlim(-a.window, 0); tr.set_ylim(0, ymax)
    k = SC["s"]
    tr.set_ylabel("picture age (s)", color=FG, fontsize=16 * k); tr.set_xlabel("seconds ago", color=FG, fontsize=14 * k)
    tr.tick_params(colors=FG, labelsize=14 * k)
    for sp in tr.spines.values():
        sp.set_color(DIM)
    hs = [Line2D([], [], color=RED, ls="--", lw=2, label="1.0 s = stale")]
    if any(t1 > lo for t0, t1 in sq):
        hs.append(Patch(color="#3b4a66", label="capacity vs range (synthetic)" if (alast or {}).get("range_model")
                        else "capacity squeeze (synthetic, seeded)"))
    if any(t1 > lo for t0, t1 in bo):
        hs.append(Patch(color=ORANGE, alpha=0.6, label="blackout"))
    tr.legend(handles=hs, loc="upper left", fontsize=13 * k, facecolor=BG, edgecolor=DIM, labelcolor=FG)

    rx = (last or {}).get("rx_hz") or {}
    for i, k in enumerate(("T0", "T1", "T2")):
        flowing = fresh and (rx.get(k) or 0) > 0.5
        boxes[i].set_facecolor(BLUE if flowing else "none"); boxes[i].set_edgecolor(BLUE if flowing else DIM)
        blabels[i].set_color(FG if flowing else DIM)
        base = blabels[i].get_text().split("\n")[0]
        shed = i > 0 and ((last or {}).get("tier") or 0) >= 3 - i       # tier = how many tiers the manager shed
        blabels[i].set_text(f"{base}\n{rx.get(k, 0):.0f} Hz" if flowing else f"{base}\n{'SHED' if shed else 'NO RX'}"
                            if fresh else base)
    if last:
        c = c_of(alast) if alast else None
        cap = "n/a" if not alast else "0 (blackout)" if alast.get("blackout") else "unlimited" if c is None else f"{c:.0f} B/s"
        rng = (alast or {}).get("range_m")
        stats.set_text((f"range {rng:.0f} m   " if rng is not None else "") +
                       f"goodput {last.get('goodput_Bps') or 0:.0f} B/s   loss {100 * (last.get('loss') or 0):.1f} %"
                       f"   C {cap}")
    poltxt.set_text(f"policy: {pol['name']}   ·   shed tiers: {(last or {}).get('tier', '—')}")
    return []


if a.snapshot:
    end = time.time() + a.secs
    while time.time() < end:
        update(); time.sleep(0.2)
    update()
    out = Path(a.snapshot)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=100, facecolor=BG)
    print(f"snapshot -> {out.resolve()}")
else:
    ani = FuncAnimation(fig, update, interval=200, cache_frame_data=False)
    plt.show()
