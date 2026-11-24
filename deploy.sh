#!/bin/bash
# Copies this folder to the Pi and installs it. Usage: ./deploy.sh [ssh-host]
set -euo pipefail
host=${1:-pizero}
cd "$(dirname "$0")"

COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --no-fflags -cf - install.sh pi |
  ssh "$host" 'work=$(mktemp -d) && tar -C "$work" -xf - && sudo "$work/install.sh"; status=$?;
    rm -rf "$work"; exit $status'
