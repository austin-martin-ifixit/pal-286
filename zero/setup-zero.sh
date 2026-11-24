#!/bin/bash
# Sets up a Raspberry Pi Zero W as the GoTEK's USB stick (see zero/README.md),
# and lets the Compaq's Pi choose its disks. Safe to run again.
# Run on the Mac, from anywhere: zero/setup-zero.sh [zero-ssh-host] [pi-ssh-host]
# The Zero needs Raspberry Pi OS Lite, user "compaq", SSH on with the
# Compaq's key (~/.ssh/id_ed25519_pi.pub), on the office Wi-Fi, and an entry
# "gotek" in ~/.ssh/config like the Pi's (zero/README.md has it).
set -euo pipefail
zero=${1:-gotek}
pi=${2:-pizero}
cd "$(dirname "$0")/.."

echo "1. The program, its start-up service, and the USB controller set to be a device"
COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --no-fflags -cf - zero/floppy zero/gotek-gadget.service |
  ssh "$zero" 'set -euo pipefail
    work=$(mktemp -d); trap "rm -rf $work" EXIT
    tar -C "$work" -xf -
    missing=$(for p in mtools dosfstools; do dpkg -s $p >/dev/null 2>&1 || echo $p; done)
    if [ -n "$missing" ]; then          # (a fresh card has no package lists yet)
      sudo apt-get update -q >/dev/null
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends $missing >/dev/null
    fi
    sudo install -m 755 "$work/zero/floppy" /usr/local/bin/floppy
    sudo install -m 644 "$work/zero/gotek-gadget.service" /etc/systemd/system/
    sudo install -d -o "$USER" -g "$USER" /var/lib/gotek /var/lib/gotek/disks
    echo libcomposite | sudo tee /etc/modules-load.d/gotek.conf >/dev/null
    # The Zero'"'"'s inner USB socket as a device, not a host. Under [all]: the
    # end of config.txt may be inside a section for some other model.
    config=/boot/firmware/config.txt
    # (Our own line exactly: Raspberry Pi OS has a dwc2 line of its own, as
    # a host, in its [cm5] section.)
    if ! grep -q "^dtoverlay=dwc2,dr_mode=peripheral" "$config"; then
      printf "\n[all]\n# The GoTEK'"'"'s USB stick (zero/setup-zero.sh)\ndtoverlay=dwc2,dr_mode=peripheral\n" | sudo tee -a "$config" >/dev/null
      sudo touch /run/gotek-reboot-needed
    fi
    sudo systemctl daemon-reload
    sudo systemctl enable gotek-gadget.service >/dev/null 2>&1'

echo "2. The Compaq's Pi may choose disks (its key may run only the floppy program)"
# (From the Pi, or with the Pi off, the copy kept from last time in
# disks/zero/gotek-key.pub: a public key, nothing secret.)
saved=disks/zero/gotek-key.pub
if key=$(ssh -o ConnectTimeout=10 "$pi" 'cat /etc/compaq/gotek-key.pub' 2>/dev/null); then
  mkdir -p disks/zero && printf '%s\n' "$key" > "$saved"
elif [ -s "$saved" ]; then
  key=$(cat "$saved"); echo "   (the Compaq's Pi isn't answering: using the copy in $saved)"
fi
case "$key" in ssh-ed25519\ *) ;; *) echo "No key on the Pi yet: run ./deploy.sh first." >&2; exit 1 ;; esac
printf '%s\n' "$key" | ssh "$zero" 'set -euo pipefail
  read -r key
  mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys
  grep -v "compaq-pi desk: floppy library" ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.new || true
  echo "restrict,command=\"/usr/local/bin/floppy\" $key" >> ~/.ssh/authorized_keys.new
  chmod 600 ~/.ssh/authorized_keys.new && mv ~/.ssh/authorized_keys.new ~/.ssh/authorized_keys'

echo "3. The disk images (disks/1200k) into the library"
for image in disks/1200k/*.img; do
  [ -e "$image" ] || { echo "   No disk images: run ./make-disks.sh first."; break; }
  name=$(basename "$image" .img)
  ssh "$zero" "/usr/local/bin/floppy put $name" < "$image" | sed 's/^/   /'
done
if ssh "$zero" '/usr/local/bin/floppy status' | grep -q nothing; then
  ssh "$zero" '/usr/local/bin/floppy insert kermit' | sed 's/^/   /' || true
fi

if ssh "$zero" '[ -e /run/gotek-reboot-needed ]'; then
  echo "4. Restarting the Zero, to make its USB socket a device (about a minute)"
  ssh "$zero" 'sudo reboot' || true
  sleep 60
  for i in $(seq 30); do ssh -o ConnectTimeout=5 "$zero" true 2>/dev/null && break; sleep 5; done
fi
echo "5. Checking"
ssh "$zero" 'systemctl is-active gotek-gadget; ls /sys/class/udc'
ssh -o ConnectTimeout=10 "$pi" 'sudo -u desk python3 -I /opt/compaq/lib/floppies.py status' ||
  echo "   (the Compaq's Pi didn't answer: when it's back, check with: ssh $pi 'sudo -u desk python3 -I /opt/compaq/lib/floppies.py status')"
echo "Done. Plug the Zero's USB socket (the inner one) into the GoTEK."
