#!/bin/bash
# Builds all of the Compaq's floppy images into disks/1200k, using mtools on
# the Pi. They're 1.2 MB 5.25" images, the Compaq's own drive type: MS-DOS 3.1
# can't read 1.44 MB disks, so the GoTEK needs FlashFloppy firmware.
# Run fetch-games.sh and fetch-dos.sh on the Pi first. The Kermit disk takes
# its cable speed from pi/opt/compaq/data/cable-speed and carries PILINK.COM
# (tools/build-pilink.sh, run here if it hasn't been).
# Usage: ./make-disks.sh [ssh-host]
set -euo pipefail
host=${1:-pizero}
cd "$(dirname "$0")"
mkdir -p disks
# Built into a new folder first: if anything fails, the old images stay.
new=$(mktemp -d disks/.new.XXXXXX)
trap 'rm -rf "$new"' EXIT

[ -f pi/opt/compaq/dos/PILINK.COM ] || tools/build-pilink.sh "$host"
COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --no-fflags -cf - disk tools/build_disks.py \
    pi/opt/compaq/dos/PILINK.COM pi/opt/compaq/data/cable-speed |
  ssh "$host" 'set -e
    work=$(mktemp -d); trap "rm -rf $work" EXIT
    tar -C "$work" -xf -
    python3 "$work/tools/build_disks.py" "$work/disk" "$work/out" >&2
    tar -C "$work/out" -cf - .' |
  tar -C "$new" -xf -
rm -rf disks/1200k disks/1440k  # 1440k: older builds
mv "$new/1200k" disks/1200k

ls -l disks/1200k
