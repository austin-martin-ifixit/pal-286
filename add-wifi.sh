#!/bin/bash
# Saves another Wi-Fi network on the Pi, which then joins it automatically
# whenever it's in range. The password is typed here, sent over SSH, and
# never shown or stored on the Mac. On the Pi it reaches NetworkManager's
# editor on standard input, so it never appears on a command line (where
# sudo would log it) or in the process list.
# The network isn't tied to one radio, so a USB Wi-Fi adapter can take over
# if the built-in one fails to start.
# Usage: ./add-wifi.sh "Network name" [ssh-host]
set -euo pipefail
ssid=${1:?Usage: ./add-wifi.sh \"Network name\" [ssh-host]}
host=${2:-pizero}

read -rsp "Password for $ssid: " psk
echo
read -rsp "Type it again: " again
echo
if [ "$psk" != "$again" ]; then
  echo "Those didn't match; nothing was changed." >&2
  exit 1
fi
if [ ${#psk} -lt 8 ]; then
  echo "Wi-Fi passwords are at least 8 characters; nothing was changed." >&2
  exit 1
fi

printf '%s\n%s\n' "$ssid" "$psk" | ssh "$host" '
  set -e
  IFS= read -r ssid; IFS= read -r psk
  if nmcli -t -f NAME connection show | grep -qxF "$ssid"; then
    # Already saved: just change the password, keeping everything else.
    printf "set wifi-sec.psk %s\nsave persistent\nquit\n" "$psk" |
      sudo nmcli connection edit id "$ssid" >/dev/null
    echo "Updated the password for \"$ssid\"."
    exit 0
  fi
  # Autoconnect goes on afterwards: with it on, "save" stops to ask first.
  printf "set 802-11-wireless.ssid %s\nset connection.autoconnect no\nset wifi-sec.key-mgmt wpa-psk\nset wifi-sec.psk %s\nsave persistent\nquit\n" \
    "$ssid" "$psk" | sudo nmcli connection edit type wifi con-name "$ssid" >/dev/null
  sudo nmcli connection modify "$ssid" connection.autoconnect yes
  echo "Saved \"$ssid\". The Pi will join it automatically when it is in range."'
