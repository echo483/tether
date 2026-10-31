# dash.py + copilot.py — run sheet and test record (sprint, 19:05)

## Run
```bash
cd ~/drone-labs/tether
~/.local/bin/uv run python tools/dash.py                       # live: logs/live/{ground,air}.jsonl, window "TETHER"
~/.local/bin/uv run python tools/dash.py --dir logs/<run_id>   # a sweep run dir (finished run: shows its last 30 s, number grey "—")
~/.local/bin/uv run python tools/fake_live.py                  # SYNTHETIC writer -> logs/fake (45 s cycle, loops)
~/.local/bin/uv run python tools/dash.py --dir logs/fake       # dash against the fake
~/.local/bin/uv run python tools/dash.py --dir logs/fake --snapshot notes/dash-snapshot.png --secs 35   # headless PNG

~/.local/bin/uv run python tools/copilot.py policy "I'm landing — altitude and battery matter most" --dry-run
~/.local/bin/uv run python tools/copilot.py policy "I'm landing — altitude and battery matter most"     # writes policy.json
~/.local/bin/uv run python tools/copilot.py policy "..." --cap 1600     # capacity override for the T0-fits check
~/.local/bin/uv run python tools/copilot.py explain --secs 60           # -> stdout + logs/live/incidents.md
```
Env: `ANTHROPIC_API_KEY` (never printed), `TETHER_MODEL` (default `claude-sonnet-4-5`). Both tools take `--dir`.

## Behaviour worth knowing
- **dash**: giant PICTURE AGE (green < 0.5, amber 0.5–1.0, red > 1.0, grey "—" when null or ground.jsonl is > 3 s old);
  link word + TETHER ON/OFF; 30 s trace, dashed 1.0 s line, blue-grey = squeeze (air `C_set`/`C_Bps` not null),
  orange = blackout (air `blackout` or ground `link == blackout`); tier boxes filled when rx_hz > 0.5, hollow with
  **SHED** when the manager's `tier` count says so, **NO RX** when nothing arrives but it is not shed (blackout);
  goodput / loss / C; `EMULATED LINK` red banner when air says `emulated`; policy name from policy.json (mtime).
  Files are reopened on shrink / inode change (tested), absent files are fine.
- air.py logs `C_Bps: 0` during a blackout and `C_set` = configured C → dash and copilot use `C_set` and ignore
  blackout rows, so a blackout is not drawn as a squeeze and does not become "capacity 0".
- **copilot policy**: sends intent + 27 census messages with B/s + current policy.json + capacity; strict JSON back.
  Names use ground.py's real names (`LINK_NODE_STATUS`, `CURRENT_MODE`, … not the census `MSG_8`; `MSG_n` aliases
  are mapped). Messages the model left out go to T2 (CONTRACT "tier 2 = everything else", printed as a note);
  unknown names, duplicates, missing HEARTBEAT/ATTITUDE in T0, T0 B/s ≥ capacity → rejected, one repair round with
  the validator's reasons, then "not written — default policy stands". Thresholds are carried over from the current
  policy (the model cannot change them). Extra keys written: `rationale`, `source`, `intent`.
  Capacity = latest non-blackout air C (synthetic squeeze) or `--cap`; goodput is **not** used as a hard bound
  (after shedding, goodput ≈ T0 load, which would reject every policy).
  Worst-case latency: 2 calls × 20 s timeout. Typical: one call.
- **copilot explain**: last N s of ticks at 1 Hz + events + air at 1 Hz (numbers only) → 3–5 line report, appended to
  `<dir>/incidents.md`. Offline it prints the offline line plus a local numbers-only summary.
- Any failure (no key, network, HTTP error, bad reply, exception) → `copilot offline — default policy stands`, exit 0.

## Tests run (19:05)
| Test | Result |
|---|---|
| fake_live managed cycle, dash snapshots at 15 s and 35 s | `notes/dash-snapshot-shed.png` (T0 only, T1/T2 SHED, C 1600), `notes/dash-snapshot.png` (BLACKOUT, red age, NO RX) |
| fake_live `--manager off` at 19 s | `notes/dash-snapshot-unmanaged.png`: 2.03 s red, STALE, TETHER OFF, loss 30 % |
| writer restart (truncate, same inode) mid-tail | trace shows only post-restart data ✓ |
| missing dir / finished sweep run dir / live Tk window 6 s | no crash ✓ (run dir shows last 30 s, NO DATA) |
| copilot both modes, no key | `copilot offline — default policy stands (no ANTHROPIC_API_KEY)`, exit 0 ✓ |
| copilot both modes, bogus key (network up) | `… (HTTPError 401)`, exit 0, key not printed ✓ |
| canned model replies (scratch harness, policy redirected to scratch) | good → diff + atomic write; no ATTITUDE in T0 / unknown name + dup / T0 2301 B/s > C 1600 → rejected ×2, not written ✓ |
| copilot-written policy through `ground.validate_policy()` | OK ✓ |
| real API run | **not run: ANTHROPIC_API_KEY is not set in this environment** |

Real `policy.json` (written by ground.py at 18:54) was not touched by any test.
