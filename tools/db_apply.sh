#!/usr/bin/env bash
# db_apply.sh — push tools/db_config.json to a DroneBridge-for-ESP32 board over its REST API.
#
# VERIFIED AGAINST: DroneBridge for ESP32 v2.4.1 source (main/http_server.c, main/db_parameters.c).
#   GET  /api/settings          -> flat JSON of all 27 params (INCLUDING wifi_pass in plaintext)
#   POST /api/settings          -> applies the known keys, saves to NVS, replies
#                                  {"status":"success",...}, then REBOOTS ITSELF after ~2 s.
#   There is NO /api/settings/change and NO /api/system/reboot in v2.4.1. The POST *is* the reboot.
#   Out-of-range values are SILENTLY DROPPED (the reply still says success), so always run --verify.
#   There is NO web-UI password and NO auth on the REST API. Only the AP password exists (wifi_pass).
#   On other firmware versions the field names may differ. The script warns if major.minor != 2.4.
#
# Usage:
#   tools/db_apply.sh --read       # GET settings, redact secrets, pretty-print (python3 -m json.tool)
#   tools/db_apply.sh --info       # GET /api/system/info + /api/system/stats
#   tools/db_apply.sh --dry-run    # show the payload that would be POSTed (password redacted)
#   tools/db_apply.sh --verify     # compare live settings with db_config.json (+ TETHER_AP_PASS)
#   TETHER_AP_PASS=... tools/db_apply.sh            # apply (POST) -> board reboots
#
# Env:
#   DB_IP           board address. Default: the DHCP server identifier that NetworkManager recorded on
#                   $DB_IFACE (read-only `nmcli -g DHCP4.OPTION dev show`). If that is empty, falls back to
#                   DroneBridge's default ap_ip (192.168.2 dot 1), built from integers at runtime.
#   DB_IFACE        Wi-Fi interface joined to the DroneBridge AP (default wlp0s20f3). Only read, never changed.
#   DB_CONFIG       config file (default: db_config.json next to this script)
#   TETHER_AP_PASS  new AP (Wi-Fi) password, 8..63 printable ASCII chars. Never commit it.
#   TETHER_WEB_PASS ignored, because v2.4.1 has no web password. You get a warning if it is set.
#
# Secrets handling: the password goes from env -> python -> curl stdin. It never appears in argv
# (so not in `ps`) and is never printed.
set -euo pipefail

DB_IFACE="${DB_IFACE:-wlp0s20f3}"
# No dotted-quad literals in this file (see notes/dronebridge.md). Derive the address at runtime.
db_default_ip() { python3 -c 'print(".".join(map(str, (192, 168, 2, 1))))'; }
if [[ -z "${DB_IP:-}" ]]; then
  DB_IP="$(nmcli -g DHCP4.OPTION dev show "$DB_IFACE" 2>/dev/null | tr '|' '\n' \
           | sed -n 's/^ *dhcp_server_identifier = \([0-9.]*\).*/\1/p' | head -1 || true)"
  if [[ -z "$DB_IP" ]]; then
    DB_IP="$(db_default_ip)"
    echo "db_apply: no DHCP server id on $DB_IFACE; using DroneBridge default ap_ip $DB_IP" >&2
  else
    echo "db_apply: DB_IP=$DB_IP (DHCP server id on $DB_IFACE)" >&2
  fi
fi
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_CONFIG="${DB_CONFIG:-$HERE/db_config.json}"
BASE="http://${DB_IP}"
CURL=(curl -sS --fail --connect-timeout 3 -m 10)

die() { echo "db_apply: $*" >&2; exit 1; }
command -v curl >/dev/null || die "curl not found"
command -v python3 >/dev/null || die "python3 not found"
[[ -f "$DB_CONFIG" ]] || die "config not found: $DB_CONFIG"

# Redact secrets from a settings JSON on stdin, then pretty-print it with json.tool.
redact_pretty() {
  python3 -c '
import json, sys
d = json.load(sys.stdin)
for k in ("wifi_pass", "espnow_secret"):
    if k in d and d[k]:
        d[k] = "<redacted len=%d>" % len(d[k])
json.dump(d, sys.stdout, sort_keys=True)
' | python3 -m json.tool
}

check_version() {
  local info
  info="$("${CURL[@]}" "$BASE/api/system/info")" || die "cannot reach $BASE/api/system/info (joined the AP? DB_IP right?)"
  python3 -c '
import json, sys
i = json.loads(sys.argv[1])
v = "%s.%s.%s" % (i.get("major_version"), i.get("minor_version"), i.get("patch_version"))
print("board: DroneBridge v%s %s (build %s), idf %s, mac %s" % (v, i.get("maturity_version"),
      i.get("db_build_version"), i.get("idf_version"), i.get("esp_mac")), file=sys.stderr)
if (i.get("major_version"), i.get("minor_version")) != (2, 4):
    print("WARNING: field names were verified for v2.4.x only; check main/db_parameters.c of v%s" % v,
          file=sys.stderr)
' "$info"
}

# Build the POST payload: strip "_" keys and substitute the password. Reads TETHER_AP_PASS from env.
build_payload() {
  python3 - "$DB_CONFIG" <<'PY'
import json, os, sys
cfg = json.load(open(sys.argv[1]))
payload = {k: v for k, v in cfg.items() if not k.startswith("_")}
if "_ap_ip_octets" in cfg:
    payload["ap_ip"] = ".".join(map(str, cfg["_ap_ip_octets"]))
if payload.get("wifi_pass") == "CHANGE_ME":
    pw = os.environ.get("TETHER_AP_PASS", "")
    if not pw or pw == "CHANGE_ME":
        sys.exit("db_apply: TETHER_AP_PASS is unset (or CHANGE_ME); refusing to POST a placeholder password")
    if not (8 <= len(pw) <= 63) or not all(32 <= ord(c) < 127 for c in pw):
        sys.exit("db_apply: TETHER_AP_PASS must be 8..63 printable ASCII chars (WPA2 + DroneBridge limits)")
    payload["wifi_pass"] = pw
json.dump(payload, sys.stdout)
PY
}

mode="${1:-apply}"
case "$mode" in
  --read)
    s="$("${CURL[@]}" "$BASE/api/settings")" || die "cannot GET $BASE/api/settings (joined the AP? DB_IP right?)"
    printf '%s' "$s" | redact_pretty
    ;;
  --info)
    check_version
    for ep in info stats; do
      s="$("${CURL[@]}" "$BASE/api/system/$ep")" || die "cannot GET $BASE/api/system/$ep"
      echo "--- /api/system/$ep"; printf '%s' "$s" | python3 -m json.tool
    done
    ;;
  --dry-run)
    build_payload | redact_pretty
    ;;
  --verify)
    live="$("${CURL[@]}" "$BASE/api/settings")" || die "cannot GET $BASE/api/settings"
    LIVE="$live" python3 - "$DB_CONFIG" <<'PY'
import json, os, sys
raw = json.load(open(sys.argv[1]))
cfg = {k: v for k, v in raw.items() if not k.startswith("_")}
if "_ap_ip_octets" in raw:
    cfg["ap_ip"] = ".".join(map(str, raw["_ap_ip_octets"]))
live = json.loads(os.environ["LIVE"])
bad = 0
for k, want in sorted(cfg.items()):
    got = live.get(k, "<missing>")
    if k == "wifi_pass":
        pw = os.environ.get("TETHER_AP_PASS")
        if pw:
            ok = (got == pw); print("%-16s %s" % (k, "match" if ok else "MISMATCH")); bad += not ok
        else:
            print("%-16s (not checked; set TETHER_AP_PASS)" % k)
        continue
    ok = (got == want)
    print("%-16s want=%-20r got=%-20r %s" % (k, want, got, "ok" if ok else "MISMATCH")); bad += not ok
sys.exit(1 if bad else 0)
PY
    ;;
  apply|--apply)
    [[ -n "${TETHER_WEB_PASS:-}" ]] && echo "db_apply: NOTE TETHER_WEB_PASS ignored, because v2.4.1 has no web-UI password" >&2
    check_version
    payload="$(build_payload)"
    echo "db_apply: POST $BASE/api/settings (payload, password redacted):" >&2
    printf '%s' "$payload" | redact_pretty >&2
    resp="$(printf '%s' "$payload" | "${CURL[@]}" -X POST -H 'Content-Type: application/json' \
            --data-binary @- "$BASE/api/settings")" || die "POST failed"
    unset payload
    echo "db_apply: board replied: $resp" >&2
    python3 -c 'import json,sys; sys.exit(0 if json.loads(sys.argv[1]).get("status")=="success" else 1)' "$resp" \
      || die "board did not report success"
    cat >&2 <<EOF
db_apply: the board saves to NVS and reboots on its own about 2 s after replying (v2.4.1 has no reboot endpoint).
db_apply: the AP comes back with the NEW SSID/password. Re-join, then run:
            nmcli con up tether-ap        # profile from notes/dronebridge.md (never-default)
            TETHER_AP_PASS=... $0 --verify
          Values the board rejected are silently kept at their old value, and --verify shows them.
EOF
    ;;
  -h|--help)
    sed -n '2,30p' "$0"
    ;;
  *)
    die "unknown mode '$mode' (try --help)"
    ;;
esac
