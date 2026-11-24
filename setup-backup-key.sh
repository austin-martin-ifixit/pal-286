#!/bin/bash
# One-time setup for backup.sh and restore.sh: makes the backup key pair.
# The private half is locked with a password you choose (typed here, never
# stored anywhere) and kept in backups/ on this Mac; the public half lets
# backup.sh lock new backups without needing the password. Keep the
# password safe: without it the backups can't be opened.
# Usage: ./setup-backup-key.sh [ssh-host]
set -euo pipefail
host=${1:-pizero}
cd "$(dirname "$0")"
mkdir -p backups
chmod 700 backups
if [ -f backups/backup-key.pem ]; then
  echo "There's already a backup key (backups/backup-key.pem); nothing changed." >&2
  exit 1
fi

echo "Choose a password for the Compaq backups (you'll type it twice)."
# Made on the Pi (its OpenSSL also does the restoring), in a private
# folder; only the password-locked key ever leaves it.
work=$(ssh "$host" 'umask 077; mktemp -d')
# Whatever happens, nothing is left behind on the Pi (the unlocked key least of all).
trap 'ssh "$host" "shred -u $work/plain.pem 2>/dev/null; rm -rf $work" 2>/dev/null || true' EXIT
ssh -t "$host" "set -e; umask 077; cd $work
  trap 'shred -u plain.pem 2>/dev/null || rm -f plain.pem' EXIT
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out plain.pem 2>/dev/null
  openssl pkey -in plain.pem -pubout -out backup-key.pub.pem
  openssl pkey -in plain.pem -aes-256-cbc -out backup-key.pem"
scp -q "$host:$work/backup-key.pem" "$host:$work/backup-key.pub.pem" backups/
chmod 600 backups/backup-key.pem
echo "Backup key ready. Now run ./backup.sh (no password needed for backups)."
