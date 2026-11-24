#!/bin/bash
# Backs up everything on the Pi that isn't in this folder, so a new SD card
# can be brought back to exactly this state (see restore.sh):
#   - settings and keys (/etc/compaq: the office password hash, the Claude
#     and FixBot keys, PAL's settings and office notes)
#   - PAL's memory (known faces, as numbers, and notes) and the photo-booth
#     portraits people chose to keep
#   - the shared session's files and settings (documents, saves, high
#     scores, the message board, the repair queue)
#   - Wi-Fi networks, the Pi's SSH identity and your login key
#   - the Whisper speech engine built for this Pi
# (Games and PAL's models aren't included: fetch-games.sh and fetch-pal.sh
# download them again.)
# The backup is locked on the Pi with the backup key's public half (made by
# setup-backup-key.sh), so no password is needed here and nothing readable
# leaves the Pi; opening it needs the password. Each run makes a new
# backups/<date>/ folder; older ones are kept.
# Usage: ./backup.sh [ssh-host]
set -euo pipefail
case ${1:-} in -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; esac
host=${1:-pizero}
cd "$(dirname "$0")"
if [ ! -f backups/backup-key.pub.pem ]; then
  echo "No backup key yet: run ./setup-backup-key.sh once first." >&2
  exit 1
fi
dest="backups/$(date +%Y-%m-%d-%H%M%S)"
mkdir -p "$dest"

work=$(ssh "$host" 'umask 077; mktemp -d')
trap 'ssh "$host" "sudo rm -rf $work" 2>/dev/null || true' EXIT
scp -q backups/backup-key.pub.pem "$host:$work/pub.pem"
ssh "$host" "set -euo pipefail; umask 077; cd $work
  # A fresh random key for this backup, itself locked with the public key.
  # (Gone again however this ends, a failure included.)
  trap 'shred -u key 2>/dev/null || rm -f key' EXIT
  openssl rand -hex 32 > key
  openssl pkeyutl -encrypt -pubin -inkey pub.pem -pkeyopt rsa_padding_mode:oaep -in key -out key.enc
  # Streamed straight into the encryption: nothing readable is written.
  paths=''
  for p in /etc/compaq /var/lib/compaq-pal /var/lib/compaq/portraits /home/desk \
           /etc/NetworkManager/system-connections /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_*_key.pub \
           /home/compaq/.ssh/authorized_keys /opt/compaq-pal; do
    sudo -n test -e \$p && paths=\"\$paths \$p\"
  done
  [ -n \"\$paths\" ] || { echo 'Nothing to back up (is sudo working?)' >&2; exit 1; }
  # (tar says 1 when a file changed while it read it, a game's save say:
  # that's still a good backup)
  { sudo -n tar -C / -czpf - --warning=no-file-changed \$paths 2>/dev/null || [ \$? -eq 1 ]; } |
    openssl enc -aes-256-cbc -pbkdf2 -salt -pass file:key -out state.enc
  shred -u key 2>/dev/null || rm -f key"
scp -q "$host:$work/state.enc" "$host:$work/key.enc" "$dest/"
size=$(du -h "$dest/state.enc" | cut -f1)
echo "Backed up the Pi to $dest ($size, encrypted)."
echo "Restore onto a new card with: ./restore.sh $dest"
