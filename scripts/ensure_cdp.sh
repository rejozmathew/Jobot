#!/usr/bin/env bash
# ensure_cdp.sh — start (or confirm) the automation Brave on CDP port 9222.
# Idempotent: if 9222 already answers, it exits 0 without relaunching.
set -uo pipefail

PORT="${CDP_PORT:-9222}"
BRAVE="${BRAVE_EXE:-C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe}"
PROFILE="${CDP_PROFILE:-C:\Users\rejoz\AppData\Local\hermes\browser\brave-cdp-apply}"
URL="${CDP_INITIAL_URL:-about:blank}"

if curl -s --max-time 3 "http://127.0.0.1:${PORT}/json/version" | grep -q '"Browser"'; then
  echo "CDP already up on ${PORT}"
  exit 0
fi

echo "Starting Brave (port ${PORT}) ..."
# Use PowerShell Start-Process to launch a detached process with clean args.
powershell.exe -NoProfile -Command \
  "Start-Process -FilePath '${BRAVE}' -ArgumentList '--remote-debugging-port=${PORT}','--user-data-dir=${PROFILE}','--no-first-run','--no-default-browser-check','${URL}'"

# Poll up to ~20s for the debug port.
for i in $(seq 1 20); do
  if curl -s --max-time 3 "http://127.0.0.1:${PORT}/json/version" | grep -q '"Browser"'; then
    echo "CDP up on ${PORT}"
    exit 0
  fi
  sleep 1
done

echo "ERROR: CDP port ${PORT} did not come up" >&2
exit 1
