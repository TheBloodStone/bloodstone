# Shared GitLab release push helpers (source from bash scripts).
# Credentials: /root/.bloodstone/gitlab.credentials (chmod 600)

bloodstone_gitlab_credentials_file() {
  echo "${BLOODSTONE_GITLAB_CREDENTIALS:-/root/.bloodstone/gitlab.credentials}"
}

bloodstone_gitlab_load_credentials() {
  local creds
  creds="$(bloodstone_gitlab_credentials_file)"
  if [[ -f "$creds" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "$creds"
    set +a
  fi
  : "${GITLAB_USER:=}"
  : "${GITLAB_PASSWORD:=}"
  : "${GITLAB_TOKEN:=}"
  : "${GITLAB_HTTPS_URL:=https://gitlab.com/bloodstone-llc-group/bloodstone-llc-project.git}"
}

bloodstone_gitlab_auth_url() {
  bloodstone_gitlab_load_credentials
  local host_path="${GITLAB_HTTPS_URL#https://}"
  host_path="${host_path#http://}"

  if [[ -n "${GITLAB_TOKEN:-}" ]]; then
    python3 - <<'PY' "$host_path" "$GITLAB_TOKEN"
import sys, urllib.parse
host_path, token = sys.argv[1], sys.argv[2]
print(f"https://oauth2:{urllib.parse.quote(token, safe='')}@{host_path}")
PY
    return 0
  fi

  if [[ -n "${GITLAB_USER:-}" && -n "${GITLAB_PASSWORD:-}" ]]; then
    python3 - <<'PY' "$host_path" "$GITLAB_USER" "$GITLAB_PASSWORD"
import sys, urllib.parse
host_path, user, password = sys.argv[1], sys.argv[2], sys.argv[3]
user_q = urllib.parse.quote(user, safe='')
pass_q = urllib.parse.quote(password, safe='')
print(f"https://{user_q}:{pass_q}@{host_path}")
PY
    return 0
  fi

  echo "https://${host_path}"
}

bloodstone_gitlab_state_file() {
  echo "${BLOODSTONE_GITLAB_STATE_FILE:-/var/lib/bloodstone/gitlab-release-state.json}"
}

bloodstone_gitlab_state_read() {
  local state_file version=""
  state_file="$(bloodstone_gitlab_state_file)"
  mkdir -p "$(dirname "$state_file")"
  if [[ -f "$state_file" ]]; then
    python3 - <<'PY' "$state_file"
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        print(json.dumps(json.load(fh)))
except Exception:
    print("{}")
PY
  else
    echo "{}"
  fi
}

bloodstone_gitlab_already_submitted() {
  local version="$1"
  bloodstone_gitlab_state_read | python3 - <<'PY' "$version"
import json, sys
version = sys.argv[1]
try:
    state = json.load(sys.stdin)
except Exception:
    state = {}
print("yes" if state.get("last_version") == version else "no")
PY
}

bloodstone_gitlab_record_submission() {
  local version="$1" tag="$2" commit="$3"
  local state_file
  state_file="$(bloodstone_gitlab_state_file)"
  mkdir -p "$(dirname "$state_file")"
  python3 - <<'PY' "$state_file" "$version" "$tag" "$commit"
import json, os, sys, time
path, version, tag, commit = sys.argv[1:5]
state = {}
if os.path.isfile(path):
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except Exception:
        state = {}
state.update({
    "last_version": version,
    "last_tag": tag,
    "last_commit": commit,
    "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
})
with open(path, "w", encoding="utf-8") as fh:
    json.dump(state, fh, indent=2)
    fh.write("\n")
PY
}

bloodstone_gitlab_min_hours_between() {
  echo "${BLOODSTONE_GITLAB_MIN_HOURS:-6}"
}

bloodstone_gitlab_too_soon() {
  local min_hours last_ts now diff_hours
  min_hours="$(bloodstone_gitlab_min_hours_between)"
  last_ts="$(bloodstone_gitlab_state_read | python3 - <<'PY'
import json, sys
from datetime import datetime, timezone
try:
    state = json.load(sys.stdin)
except Exception:
    state = {}
raw = state.get("submitted_at") or ""
if not raw:
    print("0")
    raise SystemExit
try:
    dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    print(int(dt.timestamp()))
except Exception:
    print("0")
PY
)"
  [[ "$last_ts" == "0" ]] && return 1
  now="$(date -u +%s)"
  diff_hours=$(( (now - last_ts) / 3600 ))
  (( diff_hours < min_hours ))
}