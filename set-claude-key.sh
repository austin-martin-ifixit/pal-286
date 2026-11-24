#!/bin/bash
# Saves a Claude API key on the Pi for PAL, the lobby greeter, in
# /etc/compaq/claude.env (readable only by root and PAL's own "pal" account,
# not by the shared Compaq session), after checking Anthropic accepts it.
# Create a key at https://console.anthropic.com (Settings, API keys).
# The key is typed here, sent over SSH, and never shown or stored on the Mac.
# Usage: ./set-claude-key.sh [ssh-host]
set -euo pipefail
host=${1:-pizero}

read -rsp "Claude API key: " key
echo
if [ -z "$key" ]; then
  echo "No key entered; nothing changed." >&2
  exit 1
fi

printf '%s\n' "$key" | ssh "$host" '
  set -e
  IFS= read -r key
  if ! out=$(CLAUDE_KEY="$key" python3 -c "
import json, os, sys, urllib.error, urllib.request
request = urllib.request.Request(\"https://api.anthropic.com/v1/models?limit=100\", headers={
    \"x-api-key\": os.environ[\"CLAUDE_KEY\"], \"anthropic-version\": \"2023-06-01\"})
try:
    with urllib.request.urlopen(request, timeout=20) as response:
        models = [m[\"id\"] for m in json.load(response)[\"data\"]]
except urllib.error.HTTPError as e:
    sys.exit(\"Anthropic turned the key down (check it was copied whole).\" if e.code in (401, 403)
             else f\"Anthropic answered {e.code}; try again in a minute.\")
except OSError as e:
    sys.exit(f\"Could not reach Anthropic: {e}\")
print(len(models))
" 2>&1); then
    echo "Not saved: $out" >&2
    exit 1
  fi
  sudo install -d -m 750 -g desk /etc/compaq
  # Created unreadable (umask 077), so the shared account never gets a look,
  # even for a moment; then handed to PAL.
  printf "ANTHROPIC_API_KEY=%s\n" "$key" | sudo sh -c "umask 077; cat > /etc/compaq/claude.env.new"
  if getent group pal >/dev/null; then
    sudo chown root:pal /etc/compaq/claude.env.new
    sudo chmod 640 /etc/compaq/claude.env.new
  fi
  sudo mv /etc/compaq/claude.env.new /etc/compaq/claude.env
  sudo systemctl try-restart compaq-pal.service 2>/dev/null || true
  echo "Anthropic accepted the key and it is saved on the Pi ($out models available)."'
