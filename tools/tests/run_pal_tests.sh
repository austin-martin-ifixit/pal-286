#!/bin/bash
# Runs PAL's simulator tests in one go, on the Pi, and puts the real PAL back
# whatever happens. It STOPS THE REAL PAL for about 15 minutes (the lobby's
# screen is left alone: the simulator draws on its own, sim_screen.py): only
# when the lobby is quiet, or when Austin says to.
# From the Mac:
#   ssh pizero 'mkdir -p /tmp/rig/tests' && scp tools/tests/*.py tools/tests/*.sh pizero:/tmp/rig/tests/
#   ssh pizero 'setsid nohup bash /tmp/rig/tests/run_pal_tests.sh > /tmp/rig/pal-tests.log 2>&1 &'
#   ssh pizero 'tail -f /tmp/rig/pal-tests.log'
# Usage: run_pal_tests.sh [TEST:ACCOUNT ...]   (default: the four below)
set -u
T=$(cd "$(dirname "$0")" && pwd)
tests=("$@")
[ ${#tests[@]} -gt 0 ] || tests=(new_behaviors_test.py:pal consent_test.py:desk language_test.py:pal camera_features_test.py:root)

restore() {
  sudo pkill -u pal -f '^python3 -I /opt/compaq/pal/pal.py'
  sudo pkill -u pal -f 'pal-sim/bridge.sock'; sudo pkill -u pal -f '^python3 -I -$'
  sudo -u pal tmux -L palsim kill-server 2>/dev/null
  sleep 1
  sudo systemctl start compaq-pal
  echo "=================== the real PAL is back: $(systemctl is-active compaq-pal)"
}
trap restore EXIT

bash "$T/sim_setup.sh"
# What the tests show the "camera" and say into the "microphone": a face
# (Buzz Aldrin's NASA portrait, public domain), a phone, and a few words.
mkdir -p /tmp/pal-sim/photos /tmp/pal-sim/queue
agent="CompaqPortableIII-tests/1.0 (a Raspberry Pi; one photo for a face-recognition test)"
[ -s "$T/Buzz_Aldrin.jpg" ] || curl -fsSL -A "$agent" -o "$T/Buzz_Aldrin.jpg" \
  "https://commons.wikimedia.org/wiki/Special:FilePath/Buzz_Aldrin.jpg?width=600"
[ -s "$T/phone.jpg" ] || curl -fsSL -A "$agent" -o "$T/phone.jpg" \
  "https://guide-images.cdn.ifixit.com/igi/3DrAgS2S2IaCnYj6.medium"
cp "$T/Buzz_Aldrin.jpg" "$T/phone.jpg" /tmp/pal-sim/photos/ ||
  { echo "The test photos didn't arrive (is the Pi online?): nothing run."; exit 1; }
for pair in "yes:Yes." "q1:What time is it?" "forget:Forget me."; do
  espeak-ng -v en-us+m1 -s 150 --stdout "${pair#*:}" |
    sox -t wav - -r 16000 -c 1 -b 16 "/tmp/pal-sim/queue/${pair%%:*}.wav"
done
chmod -R a+rX /tmp/pal-sim/photos /tmp/pal-sim/queue
before=$(ls /var/lib/compaq/portraits 2>/dev/null | sort)

for item in "${tests[@]}"; do
  test=${item%%:*} account=${item##*:}
  echo "=================== $test (as $account) $(date +%H:%M:%S)"
  bash "$T/run_sim.sh" fresh > /dev/null 2>&1
  sleep 2
  # (-I and the script on standard input: nothing is loaded from /tmp)
  sudo -u "$account" timeout 900 python3 -I - < "$T/$test" 2>&1 | tail -45
  echo "--- trouble in the simulated PAL's log:"
  grep -i "camera loop\|main loop\|brain:\|microphone:\|voice:\|speaker:\|memory:\|traceback" /tmp/pal-sim/pal.log | tail -6
done
# A portrait the photo-booth test saved in the real gallery: ours to clear away.
for new in $(comm -13 <(echo "$before") <(ls /var/lib/compaq/portraits 2>/dev/null | sort)); do
  sudo rm -f "/var/lib/compaq/portraits/$new" && echo "removed the test portrait $new"
done
echo "=================== done $(date +%H:%M:%S)"
