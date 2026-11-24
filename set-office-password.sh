#!/bin/bash
# Sets the office password for the Compaq's web page (http://compaq.local).
# The password is typed here and sent over SSH; the Pi keeps only a salted
# PBKDF2 hash of it, in /etc/compaq/web.env. Changing it signs everyone out.
# Usage: ./set-office-password.sh [ssh-host]
set -euo pipefail
host=${1:-pizero}

read -rsp "New office password: " password
echo
read -rsp "Type it again: " again
echo
if [ "$password" != "$again" ]; then
  echo "Those didn't match; nothing was changed." >&2
  exit 1
fi
if [ ${#password} -lt 8 ]; then
  echo "Use at least 8 characters; nothing was changed." >&2
  exit 1
fi

printf '%s\n' "$password" | ssh "$host" '
  set -e
  python3 -c "
import hashlib, os, sys
password = sys.stdin.readline().rstrip(\"\n\").encode()
salt = os.urandom(16)
iterations = 100000
digest = hashlib.pbkdf2_hmac(\"sha256\", password, salt, iterations).hex()
print(f\"OFFICE_PASSWORD=pbkdf2_sha256\${iterations}\${salt.hex()}\${digest}\")
" | sudo sh -c "umask 077; cat > /etc/compaq/web.env.new"
  sudo chown root:desk /etc/compaq/web.env.new
  sudo chmod 640 /etc/compaq/web.env.new
  sudo mv /etc/compaq/web.env.new /etc/compaq/web.env
  # Everyone signed in with the old password is signed out, and anything
  # left running on the shared account stops (the session starts afresh).
  sudo systemctl restart compaq-desk compaq-web
  echo "Office password set. Everyone was signed out; share the new one, along with http://compaq.local"'
