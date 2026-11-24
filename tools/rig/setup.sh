#!/bin/bash
# Copies the virtual Compaq test rig and the current code to the Pi's /tmp/rig
# (a reboot clears it; run this again). Run on the Mac, from anywhere:
#   tools/rig/setup.sh [ssh-host]
set -euo pipefail
host=${1:-pizero}
cd "$(dirname "$0")/../.."
# /tmp/rig is ours alone: tests run from it, so nobody else may put files there.
ssh "$host" 'if [ -e /tmp/rig ] && [ ! -O /tmp/rig ]; then echo "/tmp/rig belongs to someone else: remove it first." >&2; exit 1; fi
  mkdir -p -m 700 /tmp/rig && chmod 700 /tmp/rig && mkdir -p /tmp/rig/lib /tmp/rig/pal /tmp/rig/web /tmp/rig/c
  missing=$(for p in xvfb dosbox xdotool ffmpeg; do dpkg -s $p >/dev/null 2>&1 || echo $p; done)
  [ -z "$missing" ] || sudo apt-get install -y $missing'
scp -q tools/rig/*.sh tools/rig/*.py tools/rig/dosbox.conf tools/rig/MSKERMIT.INI disk/SERVE.INI \
       tools/build_disks.py "$host:/tmp/rig/"
scp -q pi/opt/compaq/lib/*.py "$host:/tmp/rig/lib/"
scp -q pi/opt/compaq/dos/PILINK.COM "$host:/tmp/rig/c/"      # (built by tools/build-pilink.sh)
scp -q tools/tests/pilink_test.py tools/tests/pilink_terminal_test.py tools/tests/tv_link_test.py tools/tests/video_rate.py tools/tests/doom_rate.py \
       tools/tests/floppy_test.py tools/tests/floppies_test.py zero/floppy "$host:/tmp/rig/"
scp -q pi/opt/compaq/pal/*.py "$host:/tmp/rig/pal/"
scp -q -r pi/opt/compaq/web/server.py pi/opt/compaq/web/index.html pi/opt/compaq/web/vendor "$host:/tmp/rig/web/"
ssh "$host" 'chmod +x /tmp/rig/*.sh
  if [ -f ~/build/msk316/files/MSK316.EXE ]; then echo "Rig ready in /tmp/rig on the Pi."
  else echo "MS-DOS Kermit (MSK316.EXE) is missing from ~/build/msk316 on the Pi: see fetch-dos.sh."; fi'
