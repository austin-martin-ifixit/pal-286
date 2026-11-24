# Shared helpers for menu programs. Source it: . /opt/compaq/lib/common.sh

# intro "Name" "tip"...: shows the program's name and key tips, then waits.
# Fails if the user types 0 to go back, so callers can: intro ... || exit 0
intro() {
  echo
  echo "  $1" | tr '[:lower:]' '[:upper:]'
  shift
  echo
  local line
  for line in "$@"; do
    echo "  $line"
  done
  echo "  F10 (or Ctrl-\\) any time: back to the main menu (save your work first)."
  echo
  local answer
  read -r -p "  Press Enter to start, or 0 to go back: " answer || return 1
  [ "$answer" != 0 ]
}

pause() {
  echo
  read -r -p "  Press Enter to return to the menu. " _
}

# choose LISTFILE: menu of "Name|value" lines; prints the picked value.
choose() {
  local lines line i=0 n
  mapfile -t lines < <(grep -v '^#' "$1" | grep '|')
  echo >&2
  # A long list goes in two columns, so it fits the 24-line screen.
  local half=$(( (${#lines[@]} + 1) / 2 )) left right
  if [ ${#lines[@]} -gt 14 ]; then
    for ((i = 0; i < half; i++)); do
      left=$(printf "%2d.  %s" $((i + 1)) "${lines[$i]%%|*}")
      right=""
      if [ $((i + half)) -lt ${#lines[@]} ]; then
        right=$(printf "%2d.  %s" $((i + half + 1)) "${lines[$((i + half))]%%|*}")
      fi
      printf "   %-37.37s  %-37.37s\n" "$left" "$right" >&2
    done
    i=${#lines[@]}
  else
    for line in "${lines[@]}"; do
      i=$((i + 1))
      printf "    %2d.  %s\n" "$i" "${line%%|*}" >&2
    done
  fi
  echo >&2
  echo "     0.  Back" >&2
  echo >&2
  read -r -p "  Type a number, then press Enter: " n || return 1
  [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge 1 ] && [ "$n" -le "$i" ] || return 1
  echo "${lines[$((10#$n - 1))]#*|}"
}

# Files the Compaq makes or uses live here, ready for Kermit transfers.
FILES=$HOME/compaq-files
