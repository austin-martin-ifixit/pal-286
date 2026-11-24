#!/bin/bash
# Saves a FixBot API key on the Pi, in /etc/compaq/fixbot.env (readable only by
# root and PAL's service, which makes FixBot requests for the menu), after
# checking FixBot accepts it. Anyone using the Compaq, there or on the web,
# can then ask FixBot, which uses the workspace's plan, but can't see the key. Create a key at
# https://app.fixbot.pro/workspace/settings/api-keys (workspace admins only).
# The key is typed here, sent over SSH, and never shown or stored on the Mac.
# Usage: ./set-fixbot-key.sh [ssh-host]
set -euo pipefail
host=${1:-pizero}

read -rsp "FixBot API key: " key
echo
if [ -z "$key" ]; then
  echo "No key entered; nothing changed." >&2
  exit 1
fi

printf '%s\n' "$key" | ssh "$host" '
  set -e
  IFS= read -r key
  if ! out=$(FIXBOT_KEY="$key" python3 -c "
import os, sys
sys.path.insert(0, \"/opt/compaq/lib\")
import ifixit
try:
    ifixit.check_key(os.environ[\"FIXBOT_KEY\"])
except ifixit.FixBotError as e:
    sys.exit(str(e))
" 2>&1); then
    echo "Not saved: $out" >&2
    exit 1
  fi
  printf "FIXBOT_API_KEY=%s\n" "$key" | sudo sh -c "umask 077; cat > /etc/compaq/fixbot.env.new"
  sudo chown root:pal /etc/compaq/fixbot.env.new
  sudo chmod 640 /etc/compaq/fixbot.env.new
  sudo mv /etc/compaq/fixbot.env.new /etc/compaq/fixbot.env
  echo "FixBot accepted the key and it is saved. Ask FixBot is ready in the Compaq menu."'
