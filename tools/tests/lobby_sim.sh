#!/bin/bash
# The whole lobby, privately, on the Pi: the menu's shared session, the
# serial bridge, a pretend Compaq running PI (lobby_screen.py: 640x400 dots,
# saved as /tmp/lobbysim/screen/screen.png every second) and PAL, all in a private
# mount namespace, so tmux -L compaq, /run/compaq-serial and
# /run/compaq-pal there are its own, not the lobby's. The shared account's
# home and /var/lib/compaq are copies (overlays): notes posted, saves and
# portraits vanish with the simulator.
#
# PAL's camera, microphone and speaker are folders (as in run_sim.sh), at
# the lobby's pace (PAL_SIM_REALTIME, senses.py): a WAV put in mic/ is
# spoken into a quiet room, and what PAL says lands in said/ and takes as
# long as it would to play. Nothing makes a sound. The real PAL is stopped
# while it runs (one Whisper at a time on a Pi 3): only when the lobby is
# quiet, or when Austin says to. "stop" puts the real PAL back.
#
# Usage, on the Pi:
#   bash lobby_sim.sh start            the lobby, from scratch
#   bash lobby_sim.sh keys 'TEXT'      typed on its keyboard (printf escapes: '1\r', '\e[21~' is F10)
#   bash lobby_sim.sh say FILE.wav     said into its microphone (16 kHz mono)
#   bash lobby_sim.sh face [FILE.jpg]  someone in front of its camera (none: nobody)
#   bash lobby_sim.sh text             the shared session's text, as tmux has it
#   bash lobby_sim.sh in CMD...        a command inside (as root)
#   bash lobby_sim.sh stop             all of it away, and the real PAL back
set -u
SIM=/tmp/lobbysim
T=$(cd "$(dirname "$0")" && pwd)
PATHS=/usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games

inside() { sudo nsenter -t "$(cat $SIM/ns.pid)" -m -- "$@"; }

stop() {
  if [ -s $SIM/ns.pid ]; then
    inside sh -c 'pkill -u pal -f "^python3 -I /opt/compaq/pal/pal.py"; pkill -u desk -f "^python3 -I -$";
                  runuser -u desk -- tmux -L compaq kill-server' 2>/dev/null
    sleep 1
    sudo kill "$(cat $SIM/ns.pid)" 2>/dev/null
  fi
  sudo pkill -u pal -f "^/opt/compaq-pal/bin/whisper-server" 2>/dev/null
  sudo rm -f $SIM/ns.pid
}

case "${1:-}" in
start)
  stop
  sudo systemctl stop compaq-pal
  sudo install -d -o pal -g pal -m 755 /run/compaq-pal    # (the stop took it away; the mount needs it)
  sudo rm -rf $SIM
  sudo install -d -o "$(id -u)" -m 755 $SIM     # (the logs below are written as whoever runs this)
  sudo install -d -o desk -g desk -m 750 $SIM/run-serial
  sudo install -d -o pal -g pal -m 755 $SIM/run-pal
  sudo install -d -o desk -g desk -m 700 $SIM/tmux-desk
  sudo install -d -o desk -g desk -m 755 $SIM/screen
  sudo install -d -m 755 $SIM/up $SIM/work
  sudo install -d -m 755 $SIM/up/desk $SIM/up/lib $SIM/work/desk $SIM/work/lib
  # PAL's folders: anyone may put files in them, but they're PAL's (it
  # clears away what it has heard); see sim_setup.sh.
  sudo install -d -o pal -g pal -m 1777 $SIM/camera $SIM/mic $SIM/said
  sudo install -d -o pal -g pal -m 700 $SIM/state
  # The lobby's own settings, with the folders for camera, microphone and speaker.
  { sudo cat /etc/compaq/pal.conf; printf '%s\n' "CAMERA=dir:$SIM/camera" "MICROPHONE=dir:$SIM/mic" \
      "SPEAKER=dir:$SIM/said"; } | sudo tee $SIM/pal.conf > /dev/null
  sudo chown root:pal $SIM/pal.conf; sudo chmod 640 $SIM/pal.conf
  # The namespace, held open by a sleep (its pid is how to get back in).
  sudo setsid -f unshare --mount --propagation private -- sh -c "
    mount --bind $SIM/run-serial /run/compaq-serial &&
    mount --bind $SIM/run-pal /run/compaq-pal &&
    mount --bind $SIM/tmux-desk /tmp/tmux-1001 &&
    mount -t overlay overlay -o lowerdir=/home/desk,upperdir=$SIM/up/desk,workdir=$SIM/work/desk /home/desk &&
    mount -t overlay overlay -o lowerdir=/var/lib/compaq,upperdir=$SIM/up/lib,workdir=$SIM/work/lib /var/lib/compaq &&
    echo \$\$ > $SIM/ns.pid && exec sleep infinity" > $SIM/ns.log 2>&1
  for _ in $(seq 50); do [ -s $SIM/ns.pid ] && break; sleep 0.1; done
  [ -s $SIM/ns.pid ] || { echo "The namespace didn't start:"; cat $SIM/ns.log; exit 1; }
  # The shared session (as compaq-desk.service), the screen (as compaq-tv.service), PAL (as compaq-pal.service).
  inside /opt/compaq/lib/reset-desk-home
  inside sh -c "cd /home/desk && runuser -u desk -- env -i HOME=/home/desk LANG=C LC_ALL=C COMPAQ_MENU=1 TMOUT=1800 \
    PATH=$PATHS tmux -L compaq -f /opt/compaq/tmux.conf new-session -d -s compaq -x 80 -y 24 /opt/compaq/session &&
    runuser -u desk -- tmux -L compaq set -g window-size manual"
  inside sh -c "cd /home/desk && runuser -u desk -- env -i HOME=/home/desk LANG=C LC_ALL=C PATH=$PATHS \
    setsid -f python3 -I - < $T/lobby_screen.py > $SIM/screen.log 2>&1"
  for _ in $(seq 50); do [ -S $SIM/run-serial/bridge.sock ] && break; sleep 0.2; done
  sudo /usr/sbin/nft -f /opt/compaq/pal/whisper-guard.nft
  inside sh -c "cd /tmp && runuser -u pal -g pal -G desk -G video -G audio -- env -i PATH=$PATHS LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 PAL_SETTINGS=$SIM/pal.conf STATE_DIRECTORY=$SIM/state PAL_SIM_LOG_WORDS=1 \
    PAL_SIM_REALTIME=1 setsid -f nice -n 5 python3 -I /opt/compaq/pal/pal.py > $SIM/pal.log 2>&1 < /dev/null"
  sleep 10
  echo "--- PAL:"; cat $SIM/pal.log
  echo "--- the screen:"; cat $SIM/screen.log
  ;;
keys)
  printf "${2:-}" | sudo tee $SIM/screen/keyboard > /dev/null ;;
say)
  sudo install -m 644 "$2" "$SIM/mic/$(date +%s%N).wav" ;;
face)
  if [ -n "${2:-}" ]; then sudo install -m 644 "$2" $SIM/camera/current.jpg; else sudo rm -f $SIM/camera/current.jpg; fi ;;
text)
  inside runuser -u desk -- tmux -L compaq capture-pane -p -t compaq ;;
in)
  shift; inside "$@" ;;
stop)
  stop
  sudo rm -rf $SIM
  sudo systemctl start compaq-pal
  echo "the real PAL: $(systemctl is-active compaq-pal)" ;;
*)
  sed -n '2,/^set -u/p' "$0" | sed '$d'; exit 2 ;;
esac
