#!/usr/bin/env bash
# Run from the agent host. Only disposable custody state and dummy secrets.
set -euo pipefail
umask 077

case "${1:-}" in
  --help|-h)
    printf '%s\n' 'Usage: passd-remote-e2e.sh' \
      'Run from mbp with SSH access to 0. Uses tailnet port 55461.' \
      'Creates only throwaway state. The expiry test waits 62 seconds.'
    exit 0 ;;
esac
[[ $# == 0 ]] || { printf 'Unexpected arguments.\n' >&2; exit 2; }
for tool in ssh python3 mktemp mkfifo; do
  command -v "$tool" >/dev/null || { printf 'Missing tool: %s\n' "$tool" >&2; exit 1; }
done

unset PASSD_MASTER_PASSWORD PASSD_MASTER_PASSWORD_FILE PASSD_SOCKET PASSD_DATA_DIR
export PASSD_REMOTE=100.113.138.100:55461
mkdir -p -- "$HOME/.cache"
local_dir=$(mktemp -d "$HOME/.cache/passd-e2e.XXXXXX")
capture="$local_dir/received"
response="$local_dir/response"
: > "$capture"
ssh_pid=
control_open=false
tests=(setup catalog unapproved approval denial revocation expiry use-budget gateway-admin secret-isolation)
results=(FAIL FAIL FAIL FAIL FAIL FAIL FAIL FAIL FAIL FAIL)

finish() {
  local status=$? i
  trap - EXIT HUP INT TERM
  if "$control_open"; then
    printf 'EXIT\n' >&3 || true
    exec 3>&- 4>&-
  fi
  if [[ -n "$ssh_pid" ]]; then
    # Give the remote EXIT trap time to reap its children before closing SSH.
    for ((i=0; i<50; i++)); do
      kill -0 "$ssh_pid" 2>/dev/null || break
      sleep 0.1
    done
    kill "$ssh_pid" 2>/dev/null || true
    wait "$ssh_pid" 2>/dev/null || true
  fi
  unset PASSD_AGENT_TOKEN
  rm -rf -- "$local_dir"
  printf '\n%-20s %s\n' Test Result
  for ((i=0; i<${#tests[@]}; i++)); do
    printf '%-20s %s\n' "${tests[$i]}" "${results[$i]}"
  done
  exit "$status"
}
trap finish EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Keep SSH alive as the owner of all remote children. Its stdout carries only
# the machine token and fixed control replies, never the master/dummy secret.
remote_program=$(cat <<'REMOTE'
set -euo pipefail
umask 077
export PATH="$HOME/.local/bin:$PATH"
unset PASSD_REMOTE PASSD_AGENT_TOKEN PASSD_MASTER_PASSWORD PASSD_ALLOW_PRIVATE_BROKER_TARGETS
mkdir -p -- "$HOME/.cache"
tmp=$(mktemp -d "$HOME/.cache/passd-e2e.XXXXXX")
pids=()
cleanup() {
  trap - EXIT HUP INT TERM
  local pid
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  for pid in "${pids[@]}"; do wait "$pid" 2>/dev/null || true; done
  rm -rf -- "$tmp"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
exec 2>"$tmp/control.log"
export PASSD_MASTER_PASSWORD_FILE="$tmp/master-password"
export PASSD_SOCKET="$tmp/passd.sock"
export PASSD_DATA_DIR="$tmp/data"
python3 - "$tmp" <<'PY'
import pathlib, secrets, sys
root = pathlib.Path(sys.argv[1])
for name in ("master-password", "dummy-secret"):
    (root / name).write_text(secrets.token_urlsafe(48))
PY
admin() { passd --data-dir "$tmp/data" "$@"; }
admin init >"$tmp/init.log" 2>&1
passd --data-dir "$tmp/data" serve --allow-private-broker-targets >"$tmp/daemon.log" 2>&1 &
pids+=("$!")
for ((i=0; i<200; i++)); do
  [[ -S "$PASSD_SOCKET" ]] && break
  kill -0 "${pids[0]}" 2>/dev/null || exit 1
  sleep 0.1
done
[[ -S "$PASSD_SOCKET" ]] || exit 1

python3 - "$tmp" >"$tmp/echo.log" 2>&1 <<'PY' &
import json, pathlib, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
root = pathlib.Path(sys.argv[1])
secret = (root / "dummy-secret").read_text()
class Echo(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        authenticated = self.headers.get("Authorization") == "Bearer " + secret
        body = json.dumps({"authenticated": authenticated, "headers": dict(self.headers)}).encode()
        self.send_response(200 if authenticated else 401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
server = HTTPServer(("127.0.0.1", 0), Echo)
(root / "echo-port").write_text(str(server.server_port))
server.serve_forever()
PY
pids+=("$!")
for ((i=0; i<100; i++)); do
  [[ -s "$tmp/echo-port" ]] && break
  kill -0 "${pids[1]}" 2>/dev/null || exit 1
  sleep 0.1
done
[[ -s "$tmp/echo-port" ]] || exit 1
port=$(cat "$tmp/echo-port")
admin vault create E2E >"$tmp/vault.json" 2>&1
admin item put-login --vault E2E --title Echo --password-file "$tmp/dummy-secret" >"$tmp/item.json" 2>&1
admin capability put-http e2e.echo --backing-uri pass://E2E/Echo/password \
  --scheme http --host 127.0.0.1 --port "$port" --method POST \
  --path-prefix /echo/ --inject-header Authorization --inject-prefix 'Bearer ' \
  >"$tmp/capability.json" 2>&1
# Default scopes allow requesting/invoking capabilities, with zero leases.
admin agent create e2e-agent --expiration 10m >"$tmp/agent.json" 2>&1
passd --data-dir "$tmp/data" gateway --listen 100.113.138.100:55461 >"$tmp/gateway.log" 2>&1 &
pids+=("$!")
# Probe with the dummy identity and verify this is our disposable gateway.
python3 - "$tmp" "${pids[2]}" <<'PY'
import json, os, pathlib, socket, sys, time
root = pathlib.Path(sys.argv[1])
token = json.loads((root / "agent.json").read_text())["token"]
request = json.dumps({"op": "capability.list", "agent_token": token}).encode() + b"\n"
for attempt in range(100):
    os.kill(int(sys.argv[2]), 0)
    try:
        with socket.create_connection(("100.113.138.100", 55461), timeout=1) as sock:
            sock.sendall(request)
            with sock.makefile("rb") as stream:
                result = json.loads(stream.readline())
        if result.get("ok") and [c["id"] for c in result["result"]] == ["e2e.echo"]:
            os.kill(int(sys.argv[2]), 0)
            break
    except OSError:
        pass
    time.sleep(0.1)
else:
    raise SystemExit(1)
print(token, flush=True)
PY

while read -r action request extra; do
  case "$action" in
    APPROVE|DENY|REVOKE)
      [[ "$request" =~ ^req_[A-Za-z0-9]+$ ]] || exit 1
      case "$action" in
        APPROVE)
          [[ "$extra" == 60s || "$extra" == 5m ]] || exit 1
          if admin access approve "$request" --expiration "$extra" --uses 1 >"$tmp/admin.json" 2>&1; then
            printf 'OK\n'
          else printf 'FAIL\n'; fi ;;
        DENY)
          if admin access deny "$request" --note e2e >"$tmp/admin.json" 2>&1; then
            printf 'OK\n'
          else printf 'FAIL\n'; fi ;;
        REVOKE)
          if admin access revoke "$request" >"$tmp/admin.json" 2>&1; then
            printf 'OK\n'
          else printf 'FAIL\n'; fi ;;
      esac ;;
    CHECK)
      [[ "$request" =~ ^[0-9]+$ && "$request" -le 20971520 ]] || exit 1
      head -c "$request" >"$tmp/agent-capture"
      python3 - "$tmp" <<'PY'
import base64, pathlib, sys
root = pathlib.Path(sys.argv[1])
secret = (root / "dummy-secret").read_bytes()
capture = (root / "agent-capture").read_bytes()
needles = (secret, base64.b64encode(secret), base64.b64encode(secret).rstrip(b"="),
           base64.urlsafe_b64encode(secret), secret.hex().encode(), secret.hex().upper().encode())
print("FAIL" if any(needle in capture for needle in needles) else "PASS", flush=True)
PY
      ;;
    EXIT) break ;;
    *) exit 1 ;;
  esac
done
REMOTE
)
mkfifo "$local_dir/in" "$local_dir/out"
# POSIX shell quoting also works when the remote login shell is not Bash.
remote_quoted=${remote_program//\'/\'\\\'\'}
ssh -T -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=2 0 "bash -c '$remote_quoted'" \
  <"$local_dir/in" >"$local_dir/out" 2>"$local_dir/ssh.log" &
ssh_pid=$!
exec 3<>"$local_dir/in" 4<>"$local_dir/out"
control_open=true

receive_control() {
  local i
  for ((i=0; i<120; i++)); do
    if IFS= read -r -t 1 reply <&4; then
      printf '%s\n' "$reply" >> "$capture"
      return 0
    fi
    kill -0 "$ssh_pid" 2>/dev/null || return 1
  done
  return 1
}
receive_control || { printf 'Throwaway custody setup failed.\n' >&2; exit 1; }
[[ "$reply" == pda_* && "$reply" != *' '* ]] || exit 1
export PASSD_AGENT_TOKEN="$reply"
results[0]=PASS

# Use protocol v3 directly so the capture includes every received TCP byte,
# including error envelopes. The CLI itself pre-filters remote admin commands.
wire() {
  local op=$1 params=${2:-'{}'}
  python3 - "$capture" "$response" "$op" "$params" <<'PY'
import json, os, socket, sys
capture_path, response_path, op, params = sys.argv[1:]
host, port = os.environ["PASSD_REMOTE"].rsplit(":", 1)
request = {"op": op, "params": json.loads(params),
           "agent_token": os.environ["PASSD_AGENT_TOKEN"], "reason": "e2e"}
try:
    with open(capture_path, "ab", buffering=0) as capture, open(response_path, "wb") as response:
        with socket.create_connection((host, int(port)), timeout=10) as sock:
            sock.sendall(json.dumps(request).encode() + b"\n")
            received = bytearray()
            while b"\n" not in received:
                chunk = sock.recv(65536)
                if not chunk:
                    raise OSError("incomplete response")
                capture.write(chunk)
                response.write(chunk)
                received.extend(chunk)
                if len(received) > 10485760:
                    raise OSError("oversized response")
    result = json.loads(received)
    raise SystemExit(0 if result.get("ok") else 2)
except (OSError, ValueError):
    raise SystemExit(3)
PY
}

check_response() {
  python3 - "$response" "$1" <<'PY'
import json, sys
try:
    response = json.load(open(sys.argv[1]))
    mode = sys.argv[2]
    if mode == "catalog":
        valid = response.get("ok") and [c["id"] for c in response["result"]] == ["e2e.echo"]
        valid = valid and "pass://" not in json.dumps(response)
    elif mode == "echo":
        result = response["result"]
        body = json.loads(result["body"])
        valid = response.get("ok") and result["status"] == 200 and body["authenticated"] is True
        valid = valid and body["headers"]["Authorization"] == "Bearer <concealed by passd>"
    else:
        valid = response.get("ok") is False and response["error"]["code"] == mode
    raise SystemExit(0 if valid else 1)
except (OSError, ValueError, KeyError, TypeError):
    raise SystemExit(1)
PY
}

new_request() {
  local params
  printf -v params '{"capability_id":"e2e.echo","method":"POST","path":"%s","ttl_seconds":%s,"max_uses":1}' "$1" "${2:-300}"
  wire capability.request "$params" || return 1
  request_id=$(python3 - "$response" <<'PY'
import json, sys
response = json.load(open(sys.argv[1]))["result"]
if response["status"] != "pending":
    raise SystemExit(1)
print(response["id"])
PY
  ) || return 1
  [[ "$request_id" =~ ^req_[A-Za-z0-9]+$ ]]
}

decision() {
  printf '%s %s %s\n' "$1" "$request_id" "${2:-}" >&3 || return 1
  receive_control && [[ "$reply" == OK ]]
}

invoke() {
  local params
  printf -v params '{"capability_id":"e2e.echo","method":"POST","path":"%s","body":"{}"}' "$1"
  wire capability.invoke "$params"
}

refused() {
  local status=0
  invoke "$1" || status=$?
  [[ "$status" == 2 ]] && check_response permission_denied
}

check_isolation() {
  local bytes
  bytes=$(wc -c < "$capture")
  # Stream the capture over the existing SSH connection, back to custody.
  { printf 'CHECK %s\n' "$bytes"; cat "$capture"; } >&3 || return 1
  receive_control && [[ "$reply" == PASS ]]
}

if wire capability.list && check_response catalog; then results[1]=PASS; fi
if refused /echo/approval; then results[2]=PASS; fi
if new_request /echo/approval && decision APPROVE 5m && \
    invoke /echo/approval && check_response echo; then results[3]=PASS; fi
isolation=true
check_isolation || isolation=false

if new_request /echo/denial && decision DENY && refused /echo/denial; then results[4]=PASS; fi
if new_request /echo/revocation && decision APPROVE 5m && \
    decision REVOKE && refused /echo/revocation; then results[5]=PASS; fi
if new_request /echo/expiry 60 && decision APPROVE 60s; then
  printf 'Waiting 62 seconds for the minimum 60-second lease to expire.\n'
  sleep 31
  sleep 31
  if refused /echo/expiry; then results[6]=PASS; fi
fi
if new_request /echo/budget && decision APPROVE 5m && \
    invoke /echo/budget && check_response echo && refused /echo/budget; then results[7]=PASS; fi
status=0
wire access.approve '{"request":"req_e2e"}' || status=$?
if [[ "$status" == 2 ]] && check_response forbidden_remote_op; then results[8]=PASS; fi
cat "$local_dir/ssh.log" >> "$capture"
if check_isolation && "$isolation"; then results[9]=PASS; fi
for result in "${results[@]}"; do [[ "$result" == PASS ]] || exit 1; done
