# Shared by voice-open and voice-type, PAL's helpers for the shared screen
# (run as the shared session's account). Source it.

# (never waiting on a tmux that has stopped answering: PAL is mid-sentence)
tm() { timeout 5 tmux -L compaq "$@"; }

# Seconds since someone away from the lobby (a browser, the Mac's preview)
# last pressed a key. The lobby's own screen is the tmux client the serial
# bridge runs; each client's last keypress counts (the session's activity
# time also moves when a browser merely connects).
remote_idle() {
  local latest=0 pid activity created parent
  while read -r pid activity created; do
    parent=$(ps -o args= -p "$(ps -o ppid= -p "$pid" | tr -d ' ')" 2>/dev/null)
    [[ "$parent" == *serial_bridge.py* ]] && continue
    [ "$activity" -gt "$created" ] && [ "$activity" -gt "$latest" ] && latest=$activity
  done < <(tm list-clients -F '#{client_pid} #{client_activity} #{client_created}')
  echo $(( $(date +%s) - latest ))
}

# The program running in the shared screen: the newest process at the end
# of session -> menu -> program (the menu doesn't give programs their own
# process groups, so tmux only ever sees "bash").
program_now() {
  local pid child
  pid=$(tm display-message -p -t compaq '#{pane_pid}') || return
  while child=$(pgrep -P "$pid" | sort -n | tail -1) && [ -n "$child" ]; do
    pid=$child
  done
  ps -o comm= -p "$pid"
}
