#!/bin/bash
# Puts a backup made by backup.sh onto a Pi: run it on a fresh card after
# deploy.sh (so the accounts exist), then fetch-games.sh and fetch-pal.sh
# if you like. Asks for the backup password on the Pi's side.
# Restores settings and keys, PAL's memory, the shared files, Wi-Fi
# networks and the Pi's SSH identity (so this Mac recognises it as the same
# Pi), then restarts the Compaq services. Only those things: anything else
# in the backup stops the restore before a file is written.
# Usage: ./restore.sh backups/DATE [ssh-host]
set -euo pipefail
case ${1:-} in -h|--help|"") echo "Usage: ./restore.sh backups/DATE [ssh-host]"; exit 0 ;; esac
backup=$1
host=${2:-pizero}
cd "$(dirname "$0")"
for f in "$backup/state.enc" "$backup/key.enc" backups/backup-key.pem; do
  [ -f "$f" ] || { echo "Missing $f" >&2; exit 1; }
done
if ! ssh "$host" 'id desk && id pal' >/dev/null 2>&1; then
  echo "Run ./deploy.sh first: the Pi doesn't have the Compaq's accounts yet." >&2
  exit 1
fi

work=$(ssh "$host" 'umask 077; mktemp -d')
trap 'ssh "$host" "rm -rf $work" 2>/dev/null || true' EXIT
scp -q "$backup/state.enc" "$backup/key.enc" backups/backup-key.pem "$host:$work/"
echo "Type the backup password:"
ssh -t "$host" "set -euo pipefail; umask 077; cd $work
  openssl pkeyutl -decrypt -inkey backup-key.pem -pkeyopt rsa_padding_mode:oaep -in key.enc -out key
  unpack() { openssl enc -d -aes-256-cbc -pbkdf2 -pass file:key -in state.enc; }
  # What's inside, checked against what backup.sh puts in.
  unpack | tar -tzf - > members
  grep -E '^(etc/compaq|var/lib/compaq-pal|var/lib/compaq/portraits|home/desk|etc/NetworkManager/system-connections|etc/ssh/ssh_host_[a-z0-9]+_key(\.pub)?|home/[a-z_][a-z0-9_-]*/\.ssh/authorized_keys|opt/compaq-pal)(/|$)' members |
    grep -v -E '(^|/)\.\.(/|$)' > wanted || true
  if [ \"\$(wc -l < members)\" != \"\$(wc -l < wanted)\" ]; then
    echo 'This backup has files backup.sh never puts in, so nothing was restored:' >&2
    grep -v -x -F -f wanted members | head -5 >&2
    exit 1
  fi
  # PAL writes to its memory: stopped while it's put back.
  sudo systemctl stop compaq-pal
  # Files go back with their owners by name, so new account numbers don't
  # matter. (Everything in it was checked above.)
  unpack | sudo tar -C / -xzpf -
  # A login key restored into a home without a .ssh folder: the folder must
  # be the account's own, or ssh ignores the key.
  for keys in \$(grep -o '^home/[^/]*/\\.ssh/authorized_keys' wanted | sort -u); do
    user=\$(basename \$(dirname \$(dirname \$keys)))
    sudo chown \$user: /\$(dirname \$keys) /\$keys && sudo chmod 700 /\$(dirname \$keys) && sudo chmod 600 /\$keys
  done
  shred -u key 2>/dev/null || rm -f key
  sudo nmcli connection reload || true
  sudo systemctl reload ssh
  sudo systemctl restart compaq-desk compaq-web compaq-pal
  sudo systemctl try-restart compaq-tv compaq-serial"
echo "Restored $backup."
echo "The Pi has its old SSH identity back. If ssh now warns that the host"
echo "identification changed, that's expected after a new card; clear it with:"
echo "  ssh-keygen -R $host"
echo "Then run ./deploy.sh once more to settle file permissions."
