#!/bin/bash
# Sets up the Pi's modern-web and Doom programs in their own folder,
# /opt/compaq-net: yt-dlp for PotatoTube, at the pinned version below
# (checked against its checksum), and Doom twice over, both built here from
# doom-ascii's exact v0.3.2 commit: doom-ascii itself (Doom drawn in text)
# and doom-frames (the same game handing its frames to lib/doomhd.py, for
# Doom in real dots on the Compaq; tools/doomgeneric_frames.c). (ffmpeg,
# QuickJS, the headless browser and Doom's shareware data come with
# deploy.sh.)
# YouTube changes often, and yt-dlp keeps up: when PotatoTube stops working,
# run this with --latest to install yt-dlp's newest release, checked against
# the checksums PyPI publishes for it.
# Usage: ./fetch-net.sh [--latest] [ssh-host]
set -euo pipefail
latest=no
if [ "${1:-}" = --latest ]; then latest=yes; shift; fi
case ${1:-} in -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; esac
host=${1:-pizero}
cd "$(dirname "$0")"

pins="yt-dlp==2026.8.19 --hash=sha256:1d57897e94c6665a0a6f9bc54b34e584284e32c034ffab3a7df25d8f7b24eedf
yt-dlp-ejs==0.8.0 --hash=sha256:79300e5fca7f937a1eeede11f0456862c1b41107ce1d726871e0207424f4bdb4"
if [ "$latest" = yes ]; then
  pins=$(python3 - <<'PYTHON'
import json, urllib.request
for name in ("yt-dlp", "yt-dlp-ejs"):
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=30) as r:
        data = json.load(r)
    version = data["info"]["version"]
    wheel = next(f for f in data["releases"][version] if f["filename"].endswith("-py3-none-any.whl"))
    print(f"{name}=={version} --hash=sha256:{wheel['digests']['sha256']}")
PYTHON
)
  echo "Newest from PyPI:"
  echo "$pins" | cut -d' ' -f1 | sed 's/^/  /'
fi

echo "$pins" | ssh "$host" 'set -euo pipefail
  work=$(mktemp -d); trap "rm -rf $work" EXIT
  cat > "$work/requirements.txt"
  sudo rm -rf /opt/compaq-net/venv
  sudo install -d -m 755 /opt/compaq-net
  sudo python3 -m venv /opt/compaq-net/venv
  sudo /opt/compaq-net/venv/bin/pip install -q --disable-pip-version-check --no-deps \
    --require-hashes --only-binary :all: -r "$work/requirements.txt"
  echo "yt-dlp $(/opt/compaq-net/venv/bin/yt-dlp --version) is ready for PotatoTube."'

# Doom, drawn in text (GPL, github.com/wojciech-graj/doom-ascii): built once.
ssh "$host" 'set -euo pipefail
  if [ -x /opt/compaq-net/bin/doom-ascii ]; then echo "doom-ascii is ready."; exit 0; fi
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends build-essential git >/dev/null
  build=$(mktemp -d); trap "rm -rf $build" EXIT
  git clone -q --depth 1 --branch v0.3.2 https://github.com/wojciech-graj/doom-ascii.git "$build/src"
  [ "$(git -C "$build/src" rev-parse HEAD)" = 076cf8d0ff189154980924d221b21fcfbbdd6a2c ] ||
    { echo "doom-ascii v0.3.2 isn'"'"'t the commit it should be; stopping." >&2; exit 1; }
  make -C "$build/src" -j3 >/dev/null 2>&1
  sudo install -D -m 755 "$build/src/_unix/game/doom-ascii" /opt/compaq-net/bin/doom-ascii
  echo "doom-ascii is ready."'

# Doom in real dots: the same source with one file swapped (how the game
# shows its picture and hears its keys). Rebuilt only when that file changes.
ssh "$host" 'set -euo pipefail
  work=$(mktemp -d); trap "rm -rf $work" EXIT
  cat > "$work/doomgeneric_frames.c"
  want=$(sha256sum "$work/doomgeneric_frames.c" | cut -d" " -f1)
  if [ -x /opt/compaq-net/bin/doom-frames ] &&
     [ "$(cat /opt/compaq-net/bin/doom-frames.source 2>/dev/null)" = "$want" ]; then
    echo "doom-frames is ready."; exit 0
  fi
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends build-essential git >/dev/null
  git -c advice.detachedHead=false clone -q --depth 1 --branch v0.3.2 \
    https://github.com/wojciech-graj/doom-ascii.git "$work/src"
  [ "$(git -C "$work/src" rev-parse HEAD)" = 076cf8d0ff189154980924d221b21fcfbbdd6a2c ] ||
    { echo "doom-ascii v0.3.2 isn'"'"'t the commit it should be; stopping." >&2; exit 1; }
  cp "$work/doomgeneric_frames.c" "$work/src/src/doomgeneric_ascii.c"
  nice make -C "$work/src" -j2 >/dev/null 2>&1
  sudo install -D -m 755 "$work/src/_unix/game/doom-ascii" /opt/compaq-net/bin/doom-frames
  echo "$want" | sudo tee /opt/compaq-net/bin/doom-frames.source >/dev/null
  echo "doom-frames is ready."' < tools/doomgeneric_frames.c
