# Starts PAL in simulator mode on the Pi (camera, mic and speaker are folders,
# and its screen is sim_screen.py's pretend TV, saved as
# /tmp/pal-sim/screen.png: the lobby's screen is left alone).
# Usage: bash run_sim.sh [fresh]   (fresh: forget everyone the simulator knew)
sudo systemctl stop compaq-pal
sudo pkill -u pal -f '^python3 -I /opt/compaq/pal/pal.py' ; sleep 1
sudo install -d -o pal -g pal -m 755 /run/compaq-pal
sudo /usr/sbin/nft -f /opt/compaq/pal/whisper-guard.nft
sudo sh -c "rm -rf /tmp/pal-sim/said/* /tmp/pal-sim/mic/* /tmp/pal-sim/camera/*"
[ "${1:-}" = fresh ] && sudo sh -c "rm -rf /tmp/pal-sim/state/*"
# (1777 and PAL's own: see sim_setup.sh)
sudo chown pal:pal /tmp/pal-sim/mic /tmp/pal-sim/camera /tmp/pal-sim/said
sudo chmod 1777 /tmp/pal-sim/mic /tmp/pal-sim/camera /tmp/pal-sim/said
# Its own screen (the script is read from standard input: nothing loads from /tmp).
sudo pkill -u pal -f 'pal-sim/bridge.sock'; sudo pkill -u pal -f '^python3 -I -$'
sudo -u pal tmux -L palsim kill-server 2>/dev/null
(cd /tmp/pal-sim && sudo -u pal setsid -f python3 -I - < "$(dirname "$0")/sim_screen.py" \
  > /tmp/pal-sim/screen.log 2>&1)
for _ in $(seq 50); do [ -S /tmp/pal-sim/bridge.sock ] && break; sleep 0.2; done
# FixBot: the stand-in FixBot on 127.0.0.1:8199 (fixbot_sim_test.py), whose
# key is a file a test may put in the simulator's own (PAL-only) state
# folder; with no file, FixBot is off. No iFixit login: no FixBot page.
# REAL_FIXBOT=1 uses the real FixBot's plans with the real key
# (fixbot_real_test.py); REAL_FIXBOT_PAGE=1 FixBot's own page with the real
# iFixit login (fixbot_page_test.py).
sudo rm -f /tmp/pal-sim/state/fixbot.env
fixbot=(PAL_FIXBOT_ENV=/tmp/pal-sim/state/fixbot.env FIXBOT_BASE=http://127.0.0.1:8199
        IFIXIT_SESSION_FILE=/tmp/pal-sim/state/no-ifixit-login)
[ "${REAL_FIXBOT:-}" = 1 ] && fixbot=(PAL_FIXBOT_ENV=/etc/compaq/fixbot.env
                                     IFIXIT_SESSION_FILE=/tmp/pal-sim/state/no-ifixit-login)
[ "${REAL_FIXBOT_PAGE:-}" = 1 ] && fixbot=(PAL_FIXBOT_ENV=/etc/compaq/fixbot.env)
cd /tmp/pal-sim && sudo -u pal env PAL_SETTINGS=/tmp/pal-sim/pal-sim.conf STATE_DIRECTORY=/tmp/pal-sim/state \
  COMPAQ_BRIDGE=/tmp/pal-sim/bridge.sock PYTHONUNBUFFERED=1 PAL_SIM_LOG_WORDS=1 "${fixbot[@]}" \
  setsid -f python3 -I /opt/compaq/pal/pal.py > /tmp/pal-sim/pal.log 2>&1 < /dev/null
sleep 8
pgrep -u pal -af pal.py
