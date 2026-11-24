#!/bin/bash
# The Virtual Compaq test rig: DOSBox (a CGA PC) running MS-DOS Kermit, its
# COM1 a null modem to 127.0.0.1:5555, on a hidden screen (:99).
set -e
mkdir -p /tmp/rig/c
cp ~/build/msk316/files/MSK316.EXE /tmp/rig/c/KERMIT.EXE
cp ${INI:-/tmp/rig/MSKERMIT.INI} /tmp/rig/c/MSKERMIT.INI
pgrep -f "Xvfb :99" >/dev/null || (Xvfb :99 -screen 0 800x600x24 >/dev/null 2>&1 &)
sleep 1
DISPLAY=:99 SDL_AUDIODRIVER=dummy setsid dosbox -conf /tmp/rig/dosbox.conf >/tmp/rig/dosbox.log 2>&1 < /dev/null &
