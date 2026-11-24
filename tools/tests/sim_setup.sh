#!/bin/bash
# Makes the PAL simulator's folder on the Pi (/tmp/pal-sim; a reboot clears
# it): PAL's camera, microphone and speaker become folders.
# - Pictures put in camera/ are what PAL "sees" (current.jpg is the frame).
# - WAV files in mic/ (16 kHz mono) are what it "hears". espeak-ng plus sox
#   makes them from text.
# - What it says lands in said/, as WAVs with said-NNN.txt beside them.
# Run on the Pi: bash sim_setup.sh. Then bash run_sim.sh starts the simulated
# PAL. That stops the real one, so only do it when the lobby is quiet, and
# afterwards run: sudo systemctl start compaq-pal
set -e
sudo rm -rf /tmp/pal-sim
sudo install -d -m 1777 /tmp/pal-sim
cd /tmp/pal-sim
mkdir -p camera mic said state
# Anyone may put files in these (tests run as desk, pal and root), but they
# belong to PAL, which clears away what it has heard: 1777 with PAL as the
# owner. (The sticky bit also stops a test that runs as root from following
# a link someone else left here.)
sudo chown pal:pal camera mic said
sudo chmod 1777 camera mic said
sudo chown pal:pal state
sudo chmod 700 state
cat > pal-sim.conf <<CONF
NAME=PAL 286
MODEL=claude-sonnet-5-5
SEARCHES=2
COUNTRY=US
TIMEZONE=America/New_York
QUIET_HOURS=
GREET_EVERY_HOURS=0
VOICE=mainframe
CAMERA=dir:/tmp/pal-sim/camera
MICROPHONE=dir:/tmp/pal-sim/mic
SPEAKER=dir:/tmp/pal-sim/said
CONF
chmod 644 pal-sim.conf
echo "PAL simulator folder ready: /tmp/pal-sim"
