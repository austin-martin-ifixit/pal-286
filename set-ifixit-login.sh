#!/bin/bash
# Saves the iFixit login the lobby's FixBot page uses: the "session" cookie
# of a logged-in iFixit account, in /etc/compaq/ifixit-session.env on the Pi,
# readable only by root and PAL's service, which runs that page's browser.
# The shared session (and so anyone with the office password) can't read it.
# No password is asked for or kept: only the cookie, which ends when that
# login does (logging out in the browser it came from ends it).
#
# Getting the cookie, in Chrome on the Mac: open a new incognito window, log
# in at https://www.ifixit.com with the account the lobby should use, then
# View > Developer > Developer Tools > Application > Cookies >
# https://www.ifixit.com, and copy the Value of "session". Close the
# incognito window without logging out.
#
# The cookie is typed here, sent over SSH, checked with iFixit (which says
# whose account it is), and never shown or stored on the Mac.
# Usage: ./set-ifixit-login.sh [ssh-host]
set -euo pipefail
host=${1:-pizero}

read -rsp "iFixit session cookie: " session
echo
if [ -z "$session" ]; then
  echo "Nothing entered; nothing changed." >&2
  exit 1
fi
if [[ ! $session =~ ^[A-Za-z0-9._%-]{16,200}$ ]]; then
  echo "That doesn't look like a session cookie (letters and digits only); nothing changed." >&2
  exit 1
fi

printf '%s\n' "$session" | ssh "$host" '
  set -e
  IFS= read -r session
  if ! who=$(IFIXIT_SESSION="$session" python3 -I -c "
import json, os, sys, urllib.error, urllib.request
request = urllib.request.Request(\"https://www.ifixit.com/api/2.0/user\", headers={
    \"Cookie\": \"session=\" + os.environ[\"IFIXIT_SESSION\"], \"User-Agent\": \"compaq-link/1.0\"})
try:
    user = json.load(urllib.request.urlopen(request, timeout=30))
except urllib.error.HTTPError as e:
    sys.exit(f\"iFixit did not accept that login ({e.code}).\")
except Exception as e:
    sys.exit(f\"Could not reach iFixit ({e}).\")
print(user.get(\"username\") or user.get(\"unique_username\") or \"(an account with no name)\")
" 2>&1); then
    echo "Not saved: $who" >&2
    exit 1
  fi
  printf "IFIXIT_SESSION=%s\n" "$session" | sudo sh -c "umask 077; cat > /etc/compaq/ifixit-session.env.new"
  sudo chown root:pal /etc/compaq/ifixit-session.env.new
  sudo chmod 640 /etc/compaq/ifixit-session.env.new
  sudo mv /etc/compaq/ifixit-session.env.new /etc/compaq/ifixit-session.env
  echo "Saved. The lobby FixBot page will be logged in as: $who"'
