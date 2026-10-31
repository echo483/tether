"""copilot.py — Claude at the POLICY layer, never in the control loop. Offline -> the default policy stands.

    uv run python tools/copilot.py policy "I'm landing — altitude and battery matter most" [--dry-run] [--cap 1600]
    uv run python tools/copilot.py explain [--secs 60] [--dir logs/<run_id>]
Env: ANTHROPIC_API_KEY (never printed), TETHER_MODEL (default claude-sonnet-4-5). stdlib urllib only.
"""
import argparse, json, os, sys, time, urllib.request  # noqa: E401
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from qsim import DEFAULT_TIERS  # noqa: E402  (pure data; qsim's CLI is under __main__)

CENSUS = ROOT / "notes" / "evidence" / "census-14561.json"
POLICY = ROOT / "policy.json"
OFFLINE = "copilot offline — default policy stands"
EXTRA = {8: "LINK_NODE_STATUS", 380: "TIME_ESTIMATE_TO_TARGET", 411: "CURRENT_EVENT_SEQUENCE", 436: "CURRENT_MODE"}
ALIAS = {f"MSG_{i}": n for i, n in EXTRA.items()}   # census rows say MSG_8; ground.py validates real names

def census():
    return {EXTRA.get(r["msgid"], r["name"]): round(r["Bps"], 1) for r in json.load(open(CENSUS))["rows"]}

def default_policy(names):
    t0, t1 = DEFAULT_TIERS
    return {"name": "default", "tiers": [list(t0), list(t1), [n for n in names if n not in t0 + t1]],
            "q_hi_s": 0.5, "q_lo_s": 0.1, "T_detect_s": 0.6, "T_restore_s": 3.0}

def current_policy(names):
    p = loads(POLICY.read_text()) if POLICY.exists() else None
    return p if isinstance(p, dict) and isinstance(p.get("tiers"), list) else default_policy(names)

def loads(s):
    try:
        return json.loads(s)
    except ValueError:
        return None

def jsonl(path):
    try:
        rows = [loads(ln) for ln in open(path, "rb")]
    except OSError:
        return []
    return [r for r in rows if isinstance(r, dict) and "t" in r]

def capacity(d, override):
    air = [r for r in jsonl(d / "air.jsonl") if r.get("kind") == "air" and not r.get("blackout")]
    c = air[-1].get("C_set", air[-1].get("C_Bps")) if air else None     # air.py logs C_Bps 0 in a blackout
    if override or c:
        return (override, "--cap") if override else (float(c), "air.jsonl C (synthetic squeeze)")
    return None, "unlimited" if air else "unknown"

def tier_bps(tiers, bps):
    return [round(sum(bps.get(n, 0) for n in t)) for t in tiers]

def normalize(p, names):
    """Aliases -> census names; census messages the model left out go to the bulk tier (CONTRACT default)."""
    tiers = [[ALIAS.get(str(n).upper(), str(n).upper()) for n in t] for t in p.get("tiers", []) if isinstance(t, list)]
    if len(tiers) == 3:
        miss = [n for n in names if n not in {m for t in tiers for m in t}]
        if miss:
            print(f"  note: not placed by the model -> T2 bulk: {', '.join(miss)}")
            tiers[2] += miss
    p["tiers"] = tiers
    return p

def validate_policy(p, names, bps, cap):
    t = p.get("tiers")
    if not (isinstance(t, list) and len(t) == 3 and all(isinstance(x, list) for x in t)):
        return ["tiers must be a list of exactly 3 lists"]
    flat = [n for x in t for n in x]
    err = [f"unknown message {n}" for n in sorted(set(flat) - set(names))]
    err += [f"{n} listed more than once" for n in sorted({n for n in flat if flat.count(n) > 1})]
    err += [f"{n} missing from every tier" for n in names if n not in flat]
    err += [f"tier 0 must contain {n}" for n in ("HEARTBEAT", "ATTITUDE") if n not in t[0]]
    t0 = tier_bps(t, bps)[0]
    if cap and t0 >= cap:
        err.append(f"tier 0 needs {t0} B/s but measured capacity is {cap:.0f} B/s — it cannot fit")
    return err

def claude(system, user):
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return print(f"{OFFLINE}  (no ANTHROPIC_API_KEY)")
    body = json.dumps({"model": os.environ.get("TETHER_MODEL", "claude-sonnet-4-5"), "max_tokens": 800,
                       "system": system, "messages": [{"role": "user", "content": user}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        return "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")
    except Exception as e:  # HTTP error, network down, timeout, bad JSON: never crash the demo (key never printed)
        print(f"{OFFLINE}  ({type(e).__name__} {getattr(e, 'code', '')})")
    return None

SYS_POLICY = ("You are TETHER's policy copilot. TETHER keeps a drone operator's picture fresh on a capacity-limited "
              "MAVLink telemetry downlink by shedding low-priority streams; a deterministic 5 Hz loop enforces your "
              "policy, you never control the vehicle. Reply with STRICT JSON only: no prose, no code fences.")

def do_policy(a, d):
    names = list(bps := census())
    cur = current_policy(names)
    cap, src = capacity(d, a.cap)
    ask = {"operator_intent": a.intent, "messages_Bps": bps, "current_policy": cur,
           "capacity_Bps": cap, "capacity_source": src,
           "rules": "tiers = exactly 3 lists; tier 0 is never shed, tier 2 (bulk) is shed first, then tier 1. Tier 0 "
                    "MUST contain HEARTBEAT and ATTITUDE. Use only the given names; every message in exactly one tier. "
                    "Sum of tier-0 B/s must stay well below capacity_Bps when given (aim <= 80%). Keep tier 0 minimal: "
                    "only what the operator's intent makes safety-critical.",
           "reply_shape": {"name": "short-kebab-case", "tiers": [["..."], ["..."], ["..."]],
                           "rationale": "one sentence for the operator"}}
    msg = json.dumps(ask)
    for attempt in (1, 2):                      # one repair round with the validator's reasons
        text = claude(SYS_POLICY, msg)
        if text is None:
            return 0
        p = loads(text[text.find("{"):text.rfind("}") + 1])
        err = validate_policy(normalize(p, names), names, bps, cap) if isinstance(p, dict) else ["reply not JSON"]
        if not err:
            break
        print(f"policy rejected (attempt {attempt}): " + "; ".join(err))
        msg = json.dumps(ask) + "\nYour previous reply was invalid: " + "; ".join(err) + ". Fix it."
    else:
        print("not written — default policy stands")
        return 0
    new = {"name": str(p.get("name", "copilot"))[:40], "tiers": p["tiers"],
           **{k: cur.get(k, v) for k, v in default_policy(names).items() if k.endswith("_s")},
           "rationale": str(p.get("rationale", ""))[:300], "source": "copilot", "intent": a.intent}
    where = lambda pol, n: next((i for i, t in enumerate(pol["tiers"]) if n in t), None)  # noqa: E731
    moves = [f"{n}: T{where(cur, n)} -> T{where(new, n)}" for n in names if where(cur, n) != where(new, n)]
    print(f"policy '{cur.get('name')}' -> '{new['name']}'   capacity: {cap or '—'} ({src})\n  tier B/s  "
          f"{tier_bps(cur['tiers'], bps)} -> {tier_bps(new['tiers'], bps)}\n  " + ("\n  ".join(moves) or "no tier changes")
          + f"\n  rationale: {new['rationale']}")
    if a.dry_run:
        print("dry-run: policy.json not written")
        return 0
    tmp = POLICY.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(new, indent=1) + "\n")
    os.replace(tmp, POLICY)
    print(f"wrote {POLICY} (ground.py reloads on mtime change)")
    return 0

def do_explain(a, d):
    g = jsonl(d / "ground.jsonl")
    ticks = [r for r in g if r.get("kind") == "tick"]
    if not ticks:
        print(f"no ground ticks in {d} — nothing to explain")
        return 0
    t0 = ticks[-1]["t"] - a.secs
    win = [r for r in ticks if r["t"] >= t0]
    sec = {int(r["t"] - t0): r for r in win}                                  # 1 Hz: last tick per second
    ages = [r["picture_age_s"] for r in win if r.get("picture_age_s") is not None]
    rows = [[s, r.get("picture_age_s"), r.get("link"), r.get("tier"), r.get("goodput_Bps"),
             round(100 * (r.get("loss") or 0), 1), r.get("manager")] for s, r in sorted(sec.items())]
    ev = [[round(r["t"] - t0, 1), r.get("what"), r.get("tier", r.get("msg", r.get("name"))), r.get("reason", r.get("interval_us"))]
          for r in g if r.get("kind") == "event" and r["t"] >= t0]
    air = [[round(r["t"] - t0), r.get("C_Bps"), r.get("q_bytes"), r.get("drops"), int(bool(r.get("blackout")))]
           for r in jsonl(d / "air.jsonl") if r.get("kind") == "air" and r["t"] >= t0]
    stats = {"window_s": a.secs, "picture_age_max_s": max(ages, default=None),
             "seconds_picture_older_than_1s": round(0.2 * sum(x > 1.0 for x in ages), 1),
             "seconds_blackout": round(0.2 * sum(r.get("link") == "blackout" for r in win), 1)}
    local = (f"last {a.secs:.0f} s: max picture age {stats['picture_age_max_s']} s, "
             f"{stats['seconds_picture_older_than_1s']} s older than 1 s, {stats['seconds_blackout']} s blackout, "
             f"{sum(e[1] == 'shed' for e in ev)} sheds / {sum(e[1] == 'restore' for e in ev)} restores")
    user = json.dumps({"stats": stats, "ground_1hz_cols": ["s", "picture_age_s", "link", "tiers_shed", "goodput_Bps",
                       "loss_pct", "manager_on"], "ground_1hz": rows, "events": ev,
                       "air_1hz_cols": ["s", "C_Bps(null=unlimited)", "q_bytes", "drops_cum", "blackout"],
                       "air_1hz": air})
    text = claude("You write incident reports for TETHER, a telemetry-link manager for drones. The capacity "
                  "squeeze is synthetic and seeded (say so); blackouts are real or injected outages. Plain text only.",
                  user + "\n\nWrite a 3-5 line plain-English incident report: what happened to the link, what TETHER "
                  "did (sheds/restores = MAVLink cmd 511), what the operator saw (picture age). Use the numbers and "
                  "times (s from window start). No headers, no bullets, no markdown.")
    if text is None:
        print("local summary (numbers only): " + local)
        return 0
    print(text.strip())
    with open(d / "incidents.md", "a") as f:
        f.write(f"\n## {time.strftime('%H:%M:%S')} — last {a.secs:.0f} s of {d.name}\n\n{text.strip()}\n\n_{local}_\n")
    print(f"(appended to {d / 'incidents.md'})")
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["policy", "explain"])
    ap.add_argument("intent", nargs="?", default="balanced: keep the picture fresh")
    ap.add_argument("--dir", default="logs/live"); ap.add_argument("--dry-run", action="store_true")  # noqa: E702
    ap.add_argument("--cap", type=float, default=None, help="capacity B/s override for the T0 check")
    ap.add_argument("--secs", type=float, default=60.0, help="explain: window length")
    a = ap.parse_args()
    d = Path(a.dir) if Path(a.dir).is_absolute() or Path(a.dir).exists() else ROOT / a.dir
    try:
        return do_policy(a, d) if a.mode == "policy" else do_explain(a, d)
    except Exception as e:  # last-ditch: the demo never sees a traceback
        print(f"{OFFLINE}  ({type(e).__name__}: {e})")
        return 0

if __name__ == "__main__":
    sys.exit(main())
