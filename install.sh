#!/bin/bash
# Installs the Compaq link on the Pi. Runs as root from the unpacked folder;
# deploy.sh on the Mac does all of this. Safe to re-run after changes.
# /opt/compaq is replaced wholesale, so edit the copy here, not on the Pi.
set -euo pipefail
cd "$(dirname "$0")"
admin=${COMPAQ_USER:-${SUDO_USER:-compaq}}   # your own account, for SSH and admin work
if ! id "$admin" >/dev/null 2>&1; then
  echo "No account called $admin: run with COMPAQ_USER=yourname." >&2
  exit 1
fi
desk=desk                      # the limited account the shared session runs as
pal=pal                        # PAL 286, the lobby greeter

# Everything the menus use, so a fresh SD card is one deploy away from this.
PACKAGES=(
  tmux ckermit lrzsz picocom tcpser mtools telnet iw git unattended-upgrades
  python3-serial python3-pyte
  wordgrinder sc calcurse mc qalc lynx irssi
  frotz open-adventure nethack-console moria gnuchess bsdgames
  dictd dict dict-gcide dict-jargon dict-foldoc newsboat bombadillo taskwarrior
  gtypist typespeed fortune-mod fortunes fortunes-bofh-excuses
  bastet gnugo greed nudoku robotfindskitten freesweep moon-buggy 2048 tty-solitaire
  espeak-ng sox libsox-fmt-base alsa-utils python3-opencv python3-numpy python3-pil nftables
  ffmpeg quickjs chromium-headless-shell doom-wad-shareware python3-qrcode bluez-alsa-utils
)
missing=()
for package in "${PACKAGES[@]}"; do
  dpkg -s "$package" >/dev/null 2>&1 || missing+=("$package")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "Installing: ${missing[*]}"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends "${missing[@]}"
fi

# The shared session's account: no password, no SSH, no admin rights
# (apart from shutting the Pi down), and access to the serial port.
if ! id "$desk" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash --comment "Compaq shared session" "$desk"
  passwd --lock "$desk" >/dev/null
fi
usermod -aG dialout "$desk"
usermod -aG "$desk" "$admin"   # so the admin account can read the session's settings
chmod 750 "/home/$desk"
install -d -o "$desk" -g "$desk" "/home/$desk/compaq-files"
for folder in documents spreadsheets saves chats; do
  install -d -o "$desk" -g "$desk" "/home/$desk/compaq-files/$folder"
done

rm -rf /opt/compaq.new
cp -r pi/opt/compaq /opt/compaq.new
chown -R root:root /opt/compaq.new
find /opt/compaq.new -type d -exec chmod 755 {} +
find /opt/compaq.new -type f -exec chmod 644 {} +
find /opt/compaq.new/apps -type f ! -name .title -exec chmod 755 {} +
chmod 755 /opt/compaq.new/menu /opt/compaq.new/session /opt/compaq.new/lib/*.py /opt/compaq.new/lib/reset-desk-home \
          /opt/compaq.new/lib/voice-open /opt/compaq.new/lib/voice-type /opt/compaq.new/lib/screen-watch \
          /opt/compaq.new/lib/keep-speaker-on \
          /opt/compaq.new/web/server.py /opt/compaq.new/pal/pal.py
# Which services' files change in this deploy: only those restart (so a
# deploy doesn't close the program someone has open on the Compaq).
fingerprint() {   # fingerprint ROOT UNIT PATH... : the unit and those files under ROOT
  local root=$1 unit=$2; shift 2
  # (a path or the whole folder may not exist yet: a fresh card, a new file)
  { cat "$unit" 2>/dev/null || true
    (cd "$root" 2>/dev/null && find "$@" -type f -exec sha256sum {} + 2>/dev/null | sort) || true; } |
    sha256sum | cut -d' ' -f1
}
declare -A FILES=(
  [compaq-desk]="session tmux.conf lib/reset-desk-home"
  [compaq-web]="web"
  [compaq-pal]="pal lib/ifixit.py lib/chat.py lib/pictures.py lib/fixbot_page.py lib/screen-watch data/voice-apps"
  [compaq-speaker]="lib/keep-speaker-on"
  [compaq-serial]="lib/serial_bridge.py lib/pilink.py lib/pictures.py lib/pal_screen.py lib/transfer.py data/cable-speed"
  [compaq-tv]="lib/tv_terminal.py lib/serial_bridge.py lib/pilink.py lib/pictures.py lib/pal_screen.py lib/transfer.py data/cable-speed"
)
changed=()
for service in "${!FILES[@]}"; do
  # shellcheck disable=SC2086  # (word splitting wanted: a list of paths)
  before=$(fingerprint /opt/compaq "/etc/systemd/system/$service.service" ${FILES[$service]})
  # shellcheck disable=SC2086
  after=$(fingerprint /opt/compaq.new "pi/etc/systemd/system/$service.service" ${FILES[$service]})
  [ "$before" = "$after" ] || changed+=("$service")
done

# The new tree takes the old one's place in two renames, so there's always
# one there, even if this stops halfway.
rm -rf /opt/compaq.old
if [ -e /opt/compaq ]; then mv /opt/compaq /opt/compaq.old; fi
if ! mv /opt/compaq.new /opt/compaq; then
  [ -e /opt/compaq.old ] && mv /opt/compaq.old /opt/compaq
  echo "Couldn't put the new /opt/compaq in place; the old one is back." >&2
  exit 1
fi
rm -rf /opt/compaq.old

# PAL's own account: no login, and in desk's group so it can reach the
# Compaq's screen (the bridge's socket) and read the message board.
if ! id "$pal" >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/compaq-pal --no-create-home \
          --shell /usr/sbin/nologin --comment "PAL 286 lobby greeter" "$pal"
fi
usermod -aG "$desk,video,audio" "$pal"
# Photo-booth portraits people asked PAL to keep: PAL writes, the menu reads.
install -d -o "$pal" -g "$desk" -m 2750 /var/lib/compaq/portraits

# Settings, the FixBot key and the office password hash live in /etc/compaq,
# outside what deploys replace, readable by the shared session. The Claude
# key is PAL's alone: the shared session can't read it.
install -d -m 750 -g "$desk" /etc/compaq
rm -f /etc/compaq/*.new            # left behind by an interrupted set-*.sh
for file in web.env pal.conf pal-office.txt; do
  [ -f "/etc/compaq/$file" ] && chown root:"$desk" "/etc/compaq/$file" && chmod 640 "/etc/compaq/$file"
done
# The Claude and FixBot keys and the iFixit login are PAL's alone (FixBot
# requests and FixBot's page go through PAL's service): the shared session,
# and so anyone with the office password, can't read them.
for file in claude.env fixbot.env ifixit-session.env; do
  [ -f "/etc/compaq/$file" ] && chown root:"$pal" "/etc/compaq/$file" && chmod 640 "/etc/compaq/$file"
done
# The key that signs web sign-in cookies: root's alone (systemd hands it to
# the web server), so nobody at the shared session can make a cookie.
if [ ! -s /etc/compaq/web-cookie.key ]; then
  (umask 077 && head -c 48 /dev/urandom | base64 -w0 > /etc/compaq/web-cookie.key)
fi
chown root:root /etc/compaq/web-cookie.key
chmod 600 /etc/compaq/web-cookie.key
for file in pal.conf pal-office.txt; do
  [ -e "/etc/compaq/$file" ] || install -m 640 -g "$desk" "pi/etc/compaq/$file" /etc/compaq/
done
# The key the shared session uses to ask the Pi Zero (the GoTEK's USB stick)
# for a disk (lib/floppies.py). On the Zero it may run only its floppy
# program (zero/setup-zero.sh). Here, because reset-desk-home removes
# desk's ~/.ssh each time the session starts.
if [ ! -s /etc/compaq/gotek-key ]; then
  ssh-keygen -q -t ed25519 -N "" -C "compaq-pi desk: floppy library" -f /etc/compaq/gotek-key
fi
chown "$desk:$desk" /etc/compaq/gotek-key /etc/compaq/gotek-key.pub
chmod 600 /etc/compaq/gotek-key
chmod 644 /etc/compaq/gotek-key.pub
[ -e /etc/compaq/gotek-known-hosts ] || install -m 644 -o "$desk" -g "$desk" /dev/null /etc/compaq/gotek-known-hosts
# Earlier versions of the office-notes file, as installed: swapped for the
# current one (iFixit facts and all) if nobody has written in them yet.
case "$(md5sum < /etc/compaq/pal-office.txt | cut -d' ' -f1)" in
  706d80ac11846a113bc742171b9450dc|98b71d4b2ef43aff042bf29e33181d49)
    install -m 640 -g "$desk" pi/etc/compaq/pal-office.txt /etc/compaq/ ;;
esac
# Settings added since pal.conf was installed go on the end, with their notes
# (what's there already is never changed).
python3 -I - pi/etc/compaq/pal.conf /etc/compaq/pal.conf <<'PYTHON'
import sys
template, live = sys.argv[1], sys.argv[2]
with open(live) as f:
    have = {line.split("=", 1)[0].strip() for line in f if "=" in line and not line.lstrip().startswith("#")}
add, notes = [], []
with open(template) as f:
    for line in f:
        if line.startswith("#"):
            notes.append(line)
        elif "=" in line:
            key = line.split("=", 1)[0].strip()
            if key not in have:
                add += ["\n"] + notes + [line]
                print(f"pal.conf: added the new setting {key}")
            notes = []
        else:
            notes = []
if add:
    with open(live, "a") as f:
        f.writelines(add)
PYTHON

# desk is for the shared session only: no SSH (even with a planted key) and
# no scheduled jobs, so the office password stays the only way in. The SSH
# settings are tested before reloading, so a mistake can't lock anyone out.
install -m 644 pi/etc/ssh/sshd_config.d/compaq-desk.conf /etc/ssh/sshd_config.d/
# SSH with a key only, no passwords: only once the admin account has a key
# (from ssh-copy-id), so this can never lock everyone out.
keys_only=pi/etc/ssh/sshd_config.d/01-compaq-keys-only.conf
# (checked as the admin account, the way sshd reads it: a key that account
# can't read doesn't count)
if sudo -u "$admin" grep -qsE '^[^#]*(^|[[:space:]])(ssh-|ecdsa-|sk-)[a-z0-9@.-]+ ' "$(getent passwd "$admin" | cut -d: -f6)/.ssh/authorized_keys"; then
  install -m 644 "$keys_only" /etc/ssh/sshd_config.d/
else
  echo "Note: $admin has no SSH key yet (run ssh-copy-id on the Mac), so SSH still takes passwords."
fi
if sshd -t; then
  systemctl reload ssh
else
  rm -f /etc/ssh/sshd_config.d/compaq-desk.conf /etc/ssh/sshd_config.d/01-compaq-keys-only.conf
  echo "SSH settings didn't check out, so desk could still log in over SSH. Stopping." >&2
  exit 1
fi
# Only admins (the sudo group) may use su, so the shared account can't try
# to guess its way into the admin account.
if ! grep -q "^auth.*pam_wheel.so.*group=sudo" /etc/pam.d/su; then
  sed -i '/^auth[[:space:]]\+sufficient[[:space:]]\+pam_rootok.so/a auth       required   pam_wheel.so group=sudo' /etc/pam.d/su
fi
for deny in /etc/cron.deny /etc/at.deny; do
  for user in "$desk" "$pal"; do
    grep -qx "$user" "$deny" 2>/dev/null || echo "$user" >> "$deny"
  done
done

# The admin rule, checked before it goes live (a broken one would lock sudo).
for rule in 020_compaq-desk 021_compaq-pal; do
  visudo -cqf "pi/etc/sudoers.d/$rule"
  install -m 440 "pi/etc/sudoers.d/$rule" /etc/sudoers.d/
done

# Retire the first version's login prompt on the cable.
if [ -e /etc/systemd/system/compaq-getty.service ]; then
  systemctl stop compaq-getty.service 2>/dev/null || true
  rm -f /etc/systemd/system/compaq-getty.service /etc/profile.d/compaq-menu.sh
fi

# Automatic updates from Raspberry Pi OS's own sources, and Wi-Fi kept awake.
install -m 644 pi/etc/apt/apt.conf.d/20auto-upgrades \
               pi/etc/apt/apt.conf.d/52compaq-unattended-upgrades /etc/apt/apt.conf.d/
install -m 644 pi/etc/NetworkManager/conf.d/compaq-wifi-powersave-off.conf \
               pi/etc/NetworkManager/conf.d/compaq-ethernet-steady.conf /etc/NetworkManager/conf.d/
nmcli general reload conf 2>/dev/null || true
# Wired profiles: a self-made address when there's no DHCP server, and up as
# soon as the cable is (see compaq-ethernet-steady.conf). Applies from the
# next time the cable connects; nothing is dropped now.
{ nmcli -t -f UUID,TYPE connection show 2>/dev/null || true; } | while IFS=: read -r uuid type; do
  [ "$type" = 802-3-ethernet ] && nmcli connection modify "$uuid" ipv4.link-local fallback ipv6.method link-local || true
done
systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true

install -m 644 pi/etc/udev/rules.d/99-compaq-serial.rules /etc/udev/rules.d/
install -m 644 pi/etc/tmpfiles.d/compaq-serial.conf /etc/tmpfiles.d/
systemd-tmpfiles --create /etc/tmpfiles.d/compaq-serial.conf
# A keyboard in the lobby (the TV standing in for the Compaq) mustn't be able
# to reboot the Pi: no Ctrl+Alt+Del, no SysRq.
systemctl mask ctrl-alt-del.target >/dev/null 2>&1 || true
install -m 644 pi/etc/sysctl.d/90-compaq.conf /etc/sysctl.d/
# A small log that survives restarts.
if ! cmp -s pi/etc/systemd/journald.conf.d/90-compaq.conf /etc/systemd/journald.conf.d/90-compaq.conf; then
  install -d /etc/systemd/journald.conf.d
  install -m 644 pi/etc/systemd/journald.conf.d/90-compaq.conf /etc/systemd/journald.conf.d/
  install -d -g systemd-journal -m 2755 /var/log/journal
  systemctl restart systemd-journald
  journalctl --flush 2>/dev/null || true
fi
sysctl -q -p /etc/sysctl.d/90-compaq.conf || true
install -m 644 pi/etc/systemd/system/compaq-desk.service \
               pi/etc/systemd/system/compaq-serial.service \
               pi/etc/systemd/system/compaq-web.service \
               pi/etc/systemd/system/compaq-pal.service \
               pi/etc/systemd/system/compaq-tv.service \
               pi/etc/systemd/system/compaq-speaker.service /etc/systemd/system/

systemctl daemon-reload
# Services listed in /etc/compaq/off (one name a line, like compaq-pal) stay
# off: not started, not restarted.
off() { grep -qx "$1" /etc/compaq/off 2>/dev/null; }
is_changed() { local s; for s in "${changed[@]}"; do [ "$s" = "$1" ] && return 0; done; return 1; }
# Lets PAL finish what it's saying first (up to two minutes), so a deploy
# doesn't cut someone off mid-conversation.
pal_idle() {
  python3 -I -c 'import json, socket, sys
try:
    s = socket.socket(socket.AF_UNIX); s.settimeout(3); s.connect("/run/compaq-pal/pal.sock")
    s.sendall(b"{\"op\": \"status\"}\n"); sys.exit(1 if json.loads(s.makefile().readline()).get("talking") else 0)
except Exception:
    sys.exit(0)'
}
wait_for_pal() {
  local i
  pal_idle && return 0
  echo "compaq-pal: waiting for PAL to finish talking..."
  for i in $(seq 60); do sleep 2; pal_idle && return 0; done
}
for service in compaq-desk compaq-web compaq-pal compaq-tv compaq-speaker; do
  if off "$service"; then
    systemctl disable --now "$service.service" >/dev/null 2>&1 || true
    echo "$service: off (listed in /etc/compaq/off)"
    continue
  fi
  systemctl enable "$service.service" >/dev/null 2>&1
  # The HDMI stand-in for the Compaq only runs while the Compaq's adapter
  # isn't plugged in (compaq-serial starts and stops it).
  [ "$service" = compaq-tv ] && [ -e /dev/compaq ] && continue
  if ! systemctl is-active --quiet "$service.service"; then
    systemctl start "$service.service"
  elif is_changed "$service"; then
    [ "$service" = compaq-pal ] && wait_for_pal
    systemctl restart "$service.service"
    echo "$service: restarted (it changed)"
  fi
done
is_changed compaq-serial && systemctl try-restart compaq-serial.service
udevadm control --reload-rules
# Picks up an adapter that's already plugged in.
udevadm trigger --action=add --subsystem-match=tty --sysname-match="ttyUSB*"

echo "Compaq link installed."
