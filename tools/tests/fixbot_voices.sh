#!/bin/bash
# Makes the lines fixbot_sim_test.py says to the simulated PAL that espeak
# can't say, in the Mac's Daniel voice ("Hey FixBot" comes out "Hey, big
# smart", "Show me the photo" "Show me my phone, go"), and copies them to
# the Pi.
# Run on the Mac: tools/tests/fixbot_voices.sh [ssh-host]
set -euo pipefail
host=${1:-pizero}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
while IFS='|' read -r name text; do
  say -v Daniel -o "$work/$name.aiff" "$text"
  afconvert -f WAVE -d LEI16@16000 -c 1 "$work/$name.aiff" "$work/$name.wav"
  rm "$work/$name.aiff"
done <<'LINES'
iphone|Hey FixBot, I'm trying to fix my iPhone 12 screen. Can you pull up the guide and walk me through it?
hello|Hey FixBot.
photo|Show me the photo.
picture|Take a picture of this.
whatisthis|What is this part, and what does it do?
guide|Open the guide.
nextstep|What's the next step?
LINES
COPYFILE_DISABLE=1 tar -C "$work" --no-mac-metadata --no-xattrs -cf - . |
  ssh "$host" 'mkdir -p /tmp/rig/tests/fixbot-voices && tar -C /tmp/rig/tests/fixbot-voices -xf - &&
    chmod -R a+rX /tmp/rig/tests/fixbot-voices'
echo "The voices are in $host:/tmp/rig/tests/fixbot-voices."
