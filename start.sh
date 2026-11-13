#!/usr/bin/env bash
set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

choose_port() {
  python3 - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
while port < 65536:
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", port))
    except OSError:
        port += 1
    else:
        print(port)
        break
    finally:
        probe.close()
else:
    raise SystemExit("No free local port found")
PY
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install Python, then try again." >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is required. Install Node.js, then try again." >&2
  exit 1
fi
if [[ ! -d "$PROJECT_ROOT/frontend/node_modules" ]]; then
  echo "Frontend dependencies are missing. Run: cd frontend && npm install" >&2
  exit 1
fi

API_PORT="${RFID_API_PORT:-$(choose_port 8000)}"
WEB_PORT="${RFID_WEB_PORT:-$(choose_port 5173)}"

python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port "$API_PORT" &
API_PID=$!
(cd "$PROJECT_ROOT/frontend" && VITE_API_TARGET="http://127.0.0.1:$API_PORT" node node_modules/vite/bin/vite.js --host 127.0.0.1 --port "$WEB_PORT" --strictPort) &
WEB_PID=$!

kill_tree() {
  local parent="$1"
  local children child
  children="$(pgrep -P "$parent" 2>/dev/null || true)"
  for child in $children; do
    kill_tree "$child"
  done
  kill "$parent" 2>/dev/null || true
}

cleanup() {
  trap - INT TERM EXIT
  kill_tree "$API_PID"
  kill_tree "$WEB_PID"
  wait "$API_PID" "$WEB_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Starting RFID Tyre Management..."
echo "Dashboard: http://127.0.0.1:$WEB_PORT"
echo "API (local): http://127.0.0.1:$API_PORT"
echo "ESP32 URLs: use this computer's LAN IP and port $API_PORT"
echo "Press Ctrl+C to stop both."

while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 1
done

if ! kill -0 "$API_PID" 2>/dev/null; then
  wait "$API_PID"
  exit $?
fi
wait "$WEB_PID"
