cd /tmp
for test in pal_rehearsal:desk quiz_test:root; do
  name=${test%%:*}; user=${test##*:}
  echo "===== $name"
  bash /tmp/run_sim.sh fresh > /dev/null 2>&1
  if [ "$user" = root ]; then sudo python3 -u -I /tmp/$name.py 2>&1 | grep -v "^|" | tail -30
  else sudo -u $user python3 -u -I /tmp/$name.py 2>&1 | grep -v "^|" | tail -30; fi
  grep "camera loop\|main loop\|brain:" /tmp/pal-sim/pal.log | tail -3
done
sudo pkill -u pal -f '^python3 -I /opt/compaq/pal/pal.py'
sudo systemctl start compaq-pal
echo "===== done"
