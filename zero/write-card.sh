#!/bin/bash
# Writes the Pi Zero's SD card in a USB card reader plugged into the Compaq's
# Pi: Raspberry Pi OS Lite (32-bit, which runs on the Zero W) set up for the
# floppy library, the way Raspberry Pi Imager would, with nothing to type:
#   - name gotek, user compaq: SSH with a key only (the same keys as the
#     Compaq's Pi), sudo without a password (its password is random, never
#     kept);
#   - the Pi's own Wi-Fi connection copied into the Zero's system files
#     (unlocked from 5 GHz: the Zero only has 2.4), so the Wi-Fi password
#     never leaves the Pi's root-only files;
#   - US Wi-Fi country, New York time, US keyboard.
# A one-time script on the card (firstrun.sh, run by systemd.run from
# cmdline.txt) does the rest on the first start, with Raspberry Pi's own
# helper (imager_custom), then deletes itself and restarts.
#
# Run on the Mac:  ssh pizero 'sudo bash -s' < zero/write-card.sh
# It refuses unless exactly one USB card reader holds a card under 70 GB,
# and never touches the Pi's own card. It downloads the newest Raspberry Pi
# OS Lite (32-bit) into ~/build/zero if it isn't there, checked against
# Raspberry Pi's published checksum.
# Then: the card in the Zero, power it, wait 3 or 4 minutes, and run
# zero/setup-zero.sh (see zero/README.md).
set -euo pipefail
die() { echo "write-card: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "run it as root: ssh pizero 'sudo bash -s' < zero/write-card.sh"
owner=compaq
home=$(getent passwd "$owner" | cut -d: -f6)

# The card: the one removable USB disk under 70 GB, not the one we run from.
system=$(lsblk -no PKNAME "$(findmnt -no SOURCE /)")
cards=$(lsblk -dn -b -o NAME,TRAN,RM,SIZE | awk -v sys="$system" '$2 == "usb" && $3 == 1 && $4 < 70000000000 && $1 != sys {print $1}')
[ "$(echo "$cards" | grep -c .)" = 1 ] || die "need exactly one card reader with a card in it (found: ${cards:-none})"
dev=/dev/$cards
echo "The card: $dev, $(lsblk -dn -o SIZE,MODEL "$dev" | xargs)"

# The image, newest, checked.
mkdir -p "$home/build/zero"
url=$(curl -fsSLI -o /dev/null -w "%{url_effective}" https://downloads.raspberrypi.com/raspios_lite_armhf_latest)
image="$home/build/zero/${url##*/}"
if [ ! -s "$image" ]; then
  echo "Downloading ${url##*/} from Raspberry Pi..."
  curl -fsSL --retry 2 -o "$image" "$url"
fi
curl -fsSL -o "$image.sha256" "$url.sha256"
(cd "$(dirname "$image")" && sha256sum -c --status "$(basename "$image").sha256") || die "$image doesn't match Raspberry Pi's checksum"
chown -R "$owner:$owner" "$home/build/zero"

# Write it.
for part in $(lsblk -ln -o NAME "$dev" | tail -n +2); do umount "/dev/$part" 2>/dev/null || true; done
echo "Writing $(basename "$image") to $dev..."
xz -dc "$image" | dd of="$dev" bs=4M conv=fsync status=progress
blockdev --rereadpt "$dev"; udevadm settle
boot=$(mktemp -d); root=$(mktemp -d)
trap 'umount "$boot" "$root" 2>/dev/null; rmdir "$boot" "$root"' EXIT
mount "${dev}1" "$boot"; mount "${dev}2" "$root"

# The Wi-Fi: the Pi's own connection, copied root to root.
wifi=$(nmcli -t -f NAME,TYPE connection show --active | awk -F: '$2 ~ /wireless/ {print $1; exit}')
[ -n "$wifi" ] || die "this Pi isn't on Wi-Fi: no network to copy"
uuid=$(nmcli -g connection.uuid connection show "$wifi")
src=$(grep -l "^uuid=$uuid" /etc/NetworkManager/system-connections/*.nmconnection | head -1)
[ -n "$src" ] || die "can't find the file for the Wi-Fi connection '$wifi'"
dst="$root/etc/NetworkManager/system-connections/$(basename "$src")"
sed -e '/^band=/d' -e '/^timestamp=/d' -e "s/^uuid=.*/uuid=$(cat /proc/sys/kernel/random/uuid)/" "$src" > "$dst"
chmod 600 "$dst"; chown root:root "$dst"

# The first start.
keys=$(grep -E '^(ssh-|ecdsa-|sk-)' "$home/.ssh/authorized_keys")
hash=$(openssl rand -base64 24 | openssl passwd -6 -stdin)
q() { printf '%q' "$1"; }
{
  cat <<'EOF'
#!/bin/bash
# The Pi Zero's first start (written by zero/write-card.sh): the floppy
# library's settings, then this file deletes itself and the Zero restarts.
set +e
H=/usr/lib/raspberrypi-sys-mods/imager_custom
$H set_hostname gotek
EOF
  printf '$H enable_ssh -k'
  while IFS= read -r key; do printf ' %s' "$(q "$key")"; done <<<"$keys"
  echo
  echo "/usr/lib/userconf-pi/userconf compaq $(q "$hash")"
  cat <<'EOF'
$H set_wlan_country US
echo "compaq ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/010_compaq-nopasswd
chmod 440 /etc/sudoers.d/010_compaq-nopasswd
$H set_timezone America/New_York
$H set_keymap us
rm -f /boot/firmware/firstrun.sh
sed -i 's| systemd.run.*||g' /boot/firmware/cmdline.txt
exit 0
EOF
} > "$boot/firstrun.sh"
sed -i '1 s|$| systemd.run=/boot/firmware/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target|' \
  "$boot/cmdline.txt"
sync
echo
echo "Done: the card is the Pi Zero 'gotek', on '$wifi'. Put it in the Zero and"
echo "power it (any USB power). Its first start takes 3 or 4 minutes and restarts"
echo "once; then, from the Mac: zero/setup-zero.sh"
