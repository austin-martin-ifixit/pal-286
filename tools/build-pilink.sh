#!/bin/bash
# Assembles dos/pilink.asm (the Compaq's fast picture program) into
# pi/opt/compaq/dos/PILINK.COM, with nasm on the Pi, so the Mac needs
# nothing installed. Run it after changing pilink.asm, then ./make-disks.sh
# (PILINK.COM goes on the Kermit disk) and ./deploy.sh.
# Usage: tools/build-pilink.sh [ssh-host]
set -euo pipefail
host=${1:-pizero}
cd "$(dirname "$0")/.."
mkdir -p pi/opt/compaq/dos
ssh "$host" 'set -e
  command -v nasm >/dev/null ||
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends nasm >&2
  work=$(mktemp -d); trap "rm -rf $work" EXIT
  cat > "$work/pilink.asm"
  nasm -f bin -o "$work/PILINK.COM" "$work/pilink.asm" >&2
  cat "$work/PILINK.COM"' < dos/pilink.asm > pi/opt/compaq/dos/PILINK.COM.new
mv pi/opt/compaq/dos/PILINK.COM.new pi/opt/compaq/dos/PILINK.COM
echo "PILINK.COM: $(wc -c < pi/opt/compaq/dos/PILINK.COM | tr -d ' ') bytes"
