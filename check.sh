#!/bin/bash
# Health check for the Compaq link: one look at everything that matters,
# from the Pi's temperature to whether the web page answers.
# Usage: ./check.sh [ssh-host]
set -uo pipefail
case ${1:-} in -h|--help) echo "Usage: ./check.sh [ssh-host]"; exit 0 ;; esac
host=${1:-pizero}
cd "$(dirname "$0")"

echo "COMPAQ LINK HEALTH CHECK  $(date '+%a %d %b %Y %H:%M')"
if ! error=$(ssh -o BatchMode=yes -o ConnectTimeout=15 "$host" true 2>&1); then
  echo "  FAIL  Can't reach the Pi over SSH as '$host':"
  printf '%s\n' "$error" | grep -v '^@\|^$' | head -4 | sed 's/^/          /'
  if grep -q "IDENTIFICATION HAS CHANGED\|Host key verification failed" <<<"$error"; then
    echo "        The Pi has a new SSH identity (a new SD card, or a fresh install)."
    echo "        If that's expected: ssh-keygen -R $host   then run this again."
  else
    echo "        Is it on and on the network?"
  fi
  exit 1
fi

ssh -o BatchMode=yes "$host" 'bash -s' <<'REMOTE'
ok()   { printf "  OK    %s\n" "$*"; }
warn() { printf "  WARN  %s\n" "$*"; }
fail() { printf "  FAIL  %s\n" "$*"; }

echo
echo "THE PI"
ok "$(tr -d '\0' < /proc/device-tree/model), up $(uptime -p | sed 's/^up //')"
temp=$(vcgencmd measure_temp | grep -oE '[0-9]+' | head -1)
if [ "$temp" -lt 70 ]; then ok "Temperature ${temp} C"; else warn "Running hot: ${temp} C"; fi
throttled=$(( $(vcgencmd get_throttled | cut -d= -f2) ))
if (( throttled & 0x10001 )); then
  warn "Under-voltage since boot: use a 5 V 2.5 A supply (PAL's webcam and mic draw power too)"
else
  ok "Power supply is keeping up"
fi
if (( throttled & 0xC000C )); then
  warn "Got hot enough to slow down since boot: a heatsink or fan case helps, especially with PAL"
fi
free_gb=$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
if [ "$free_gb" -ge 2 ]; then ok "${free_gb} GB free on the SD card"; else warn "Only ${free_gb} GB free on the SD card"; fi
if [ "$(timedatectl show -p NTPSynchronized --value)" = yes ]; then ok "Clock is synced"
else warn "Clock isn't synced to the internet"; fi

echo
echo "NETWORK"
conn=$(nmcli -t -f NAME,DEVICE connection show --active | grep -v '^lo:' | head -1)
dev=${conn##*:}
if [ -n "$conn" ]; then
  freq=$(/usr/sbin/iw dev "$dev" link 2>/dev/null | awk '/freq:/{print int($2)}')
  signal=$(/usr/sbin/iw dev "$dev" link 2>/dev/null | awk '/signal:/{print $2}')
  if [ -n "$freq" ] && [ "$freq" -ge 5000 ]; then
    ok "On ${conn%%:*} via $dev, 5 GHz (${freq} MHz), signal ${signal} dBm"
  elif [ -n "$freq" ]; then
    warn "On ${conn%%:*} via $dev but 2.4 GHz (${freq} MHz): expect lag"
  else
    ok "On ${conn%%:*} via $dev"
  fi
else
  fail "Not connected to any network"
fi
radios=$(ls -d /sys/class/net/wlan* 2>/dev/null | wc -l)
if [ "$radios" -ge 2 ]; then ok "$radios Wi-Fi radios working (built-in plus USB backup)"
else warn "$radios Wi-Fi radio working: the backup isn't there (built-in chip or USB adapter missing)"; fi
gw=$(ip route | awk '/default/{print $3; exit}')
avg=$(ping -c 5 -i 0.3 -W 2 "$gw" 2>/dev/null | awk -F/ '/rtt/{print int($5)}')
if [ -z "$avg" ]; then fail "Router ($gw) didn't answer"
elif [ "$avg" -le 50 ]; then ok "Router answers in ${avg} ms on average"
else warn "Router answers slowly: ${avg} ms on average"; fi

echo
echo "THE COMPAQ LINK"
for unit in compaq-desk compaq-web; do
  if systemctl is-active --quiet "$unit"; then ok "$unit is running"; else fail "$unit isn't running"; fi
done
failed=$(systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' | tr '\n' ' ')
if [ -z "$failed" ]; then ok "No failed services"; else warn "Failed services: $failed(see: journalctl -u NAME)"; fi
if [ -s /etc/compaq/off ]; then warn "Turned off on purpose (/etc/compaq/off): $(tr '\n' ' ' < /etc/compaq/off)"; fi
if [ -e /dev/compaq ]; then
  link=$(cat /run/compaq-serial/status 2>/dev/null)
  if ! systemctl is-active --quiet compaq-serial; then fail "Serial adapter plugged in but the bridge isn't running"
  elif [ "$link" = connected ]; then
    if [ "$(cat /run/compaq-serial/terminal 2>/dev/null)" = pilink ]; then
      ok "Serial adapter plugged in, and the Compaq is connected (PI.BAT: PILINK is its terminal)"
    else ok "Serial adapter plugged in, and the Compaq is connected (Kermit is running)"; fi
  else warn "Serial adapter plugged in, bridge running: ${link:-no status} (type PI on the Compaq)"; fi
elif systemctl is-active --quiet compaq-tv; then
  ok "No serial adapter yet: the HDMI display is standing in for the Compaq"
else
  warn "Serial adapter not plugged in (fine until the Compaq is connected)"
fi
if [ -s /etc/compaq/web.env ]; then ok "Office password is set"; else warn "Office password isn't set: run set-office-password.sh"; fi
if sudo grep -qs FIXBOT_API_KEY /etc/compaq/fixbot.env; then ok "FixBot key is set"; else warn "No FixBot key yet: run set-fixbot-key.sh when you have one"; fi
watching=$(cat /run/compaq-web/viewers 2>/dev/null || echo 0)
ok "${watching} browser(s) watching right now"
if [ -x /opt/compaq-net/venv/bin/yt-dlp ] && [ -x /opt/compaq-net/bin/doom-ascii ]; then
  ok "PotatoTube and Doom are set up (yt-dlp $(/opt/compaq-net/venv/bin/yt-dlp --version 2>/dev/null))"
else
  warn "PotatoTube or Doom isn't set up: run fetch-net.sh"
fi
if [ -x /opt/compaq-net/bin/doom-frames ]; then ok "Doom in real dots is set up"
else warn "Doom in real dots isn't built yet: run fetch-net.sh (it plays in text meanwhile)"; fi
speed=$(head -1 /opt/compaq/data/cable-speed 2>/dev/null)
pilink=$(cat /run/compaq-serial/pilink 2>/dev/null)
case $pilink in
  "") ok "Cable speed for Kermit: ${speed:-9600} baud. No picture shown yet, so PILINK hasn't been tried" ;;
  *baud*) ok "Cable speed for Kermit: ${speed:-9600} baud. Pictures go through PILINK at $pilink" ;;
  *) warn "Pictures go through Kermit, slowly: PILINK is $pilink (it's on the Kermit disk: ./make-disks.sh)" ;;
esac
games=$(ls /var/lib/compaq/games 2>/dev/null | wc -l)
if [ "$games" -ge 8 ]; then ok "$games text adventures installed"; else warn "Only $games text adventures: run fetch-games.sh"; fi

echo
echo "PAL 286 (THE LOBBY GREETER)"
if systemctl is-active --quiet compaq-pal; then ok "compaq-pal is running"; else fail "compaq-pal isn't running"; fi
if sudo test -s /etc/compaq/claude.env; then ok "Claude key is set"; else warn "No Claude key: run set-claude-key.sh"; fi
models=/var/lib/compaq/pal-models
if [ -x /opt/compaq-pal/bin/whisper-server ] && [ -f $models/ggml-tiny.en-q8_0.bin ] &&
   [ -f $models/face_recognition_sface_2021dec_int8.onnx ]; then ok "Speech and face models installed"
else warn "PAL's models or speech engine are missing: run fetch-pal.sh"; fi
python3 - <<'PY'
import json, socket
def line(level, text): print(f"  {level:<6}{text}")
try:
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(5); s.connect("/run/compaq-pal/pal.sock")
        s.sendall(b'{"op": "status"}\n')
        st = json.loads(s.makefile().readline())
except (OSError, ValueError) as e:
    line("FAIL", f"PAL didn't answer ({e})")
else:
    for name, value, hint in (("Camera", st["camera"], "plug in a USB webcam"),
                              ("Microphone", st["microphone"], "most webcams have one built in"),
                              ("Speaker", st["speaker"], "plug powered speakers into the Pi's headphone socket, or a USB speaker"),
                              ("Claude", st["brain"], "run set-claude-key.sh")):
        good = str(value).startswith(("ok", "test", "writing"))
        line("OK" if good else "WARN", f"{name}: {value}" + ("" if good else f" ({hint})"))
    line("OK", f"Knows {st['people']} face(s); greeted {st['greeted_today']} today; model {st['model']}"
         + ("; in quiet mode or quiet hours" if st["asleep"] else ""))
PY
conf=$(sudo cat /etc/compaq/pal.conf 2>/dev/null)
setting() { sed -n "s/^$1=//p" <<<"$conf" | tail -1; }
ok "Voice $(setting VOICE) at $(setting SPEED) words a minute; quiet hours: $(setting QUIET_HOURS | grep . || echo none); tips: $(setting TIPS | grep . || echo yes)"
if [ -z "$(setting CITY)" ]; then ok "CITY isn't set in pal.conf, so the weather goes by the network's location (usually right)"; fi
# A Bluetooth speaker switches itself off after a quiet while; PAL then talks
# into the Pi's headphone socket, which says "ok" but is silent.
speaker=$(setting SPEAKER)
if [[ "$speaker" == bluealsa:DEV=* ]]; then
  mac=${speaker#bluealsa:DEV=}; mac=${mac%%,*}
  if bluetoothctl info "$mac" 2>/dev/null | grep -q "Connected: yes"; then
    ok "Bluetooth speaker connected ($(bluetoothctl info "$mac" | sed -n 's/^\s*Name: //p'))"
  else
    warn "Bluetooth speaker $mac isn't connected (switched off? press its power button: the Pi reconnects within 20 seconds)"
  fi
elif [[ -z "$speaker" || "$speaker" == *CARD=Headphones* ]] && [ "$(setting SPEAKER_KEEP_AWAKE)" != no ]; then
  # (the Pi can't tell whether anything is plugged into its socket)
  if pgrep -f "keep-awake.raw" >/dev/null; then
    ok "Speaker on the headphone socket (aux), with the keep-awake tone playing"
  else
    warn "The keep-awake tone isn't playing, so a speaker on the aux cord may switch itself off (journalctl -u compaq-speaker)"
  fi
fi

echo
echo "UPDATES"
pending=$(apt list --upgradable 2>/dev/null | grep -c upgradable)
if systemctl is-enabled --quiet unattended-upgrades 2>/dev/null; then ok "Automatic updates are on"
else warn "Automatic updates are off"; fi
if [ "$pending" -eq 0 ]; then ok "Nothing waiting to install"; else ok "$pending update(s) waiting (installed automatically)"; fi
if [ -f /run/reboot-required ]; then warn "An update needs a reboot to finish"; fi
REMOTE

echo
echo "FROM THIS MAC"
state=$(curl -s -m 8 http://compaq.local/api/state)
if [ -n "$state" ]; then
  echo "  OK    http://compaq.local answers: $state"
else
  # Not on the office network (the Pi was reached some other way): ask the Pi for its own page.
  state=$(ssh -o BatchMode=yes "$host" 'curl -s -m 8 -H "Host: compaq.local" http://localhost/api/state')
  if [ -n "$state" ]; then
    echo "  OK    The web page answers on the Pi: $state"
    echo "        (This Mac isn't on the Pi's network. To see the page from here:"
    echo "        ssh -N -L 8080:localhost:80 $host   then open http://localhost:8080)"
  else
    echo "  FAIL  http://compaq.local didn't answer"
  fi
fi
newest=$(ls -d backups/20*/ 2>/dev/null | sort | tail -1)
if [ -z "$newest" ]; then
  echo "  WARN  No backups yet: run ./setup-backup-key.sh once, then ./backup.sh"
else
  age=$(( ( $(date +%s) - $(stat -f %m "$newest/state.enc" 2>/dev/null || stat -c %Y "$newest/state.enc") ) / 86400 ))
  if [ "$age" -le 7 ]; then echo "  OK    Newest backup: ${newest%/} ($age day(s) old)"
  else echo "  WARN  Newest backup is $age days old (${newest%/}): run ./backup.sh"; fi
fi
