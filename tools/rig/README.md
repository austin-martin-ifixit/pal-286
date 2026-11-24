# The virtual Compaq: a test rig

Tests what the real Compaq will see, without the Compaq. It runs the real
MS-DOS Kermit 3.16 and the real PILINK.COM (the programs the Compaq runs) in
DOSBox, a CGA PC at roughly a 286's speed, on a hidden screen on the Pi.
Its COM1 is a null modem to TCP port 5555. Each test starts:

- a **private copy of the serial bridge**, on a pseudo-terminal joined to
  that port and paced at 9600 baud like a real cable;
- a **private tmux server** (`tmux -L rigtest`).

It types keys as the Compaq would send them, and takes screenshots. Nothing
touches the lobby's shared screen or the real PAL.

**Setup**, on the Mac: `tools/rig/setup.sh`. It copies the rig, the current
code and `PILINK.COM` (as last built by `tools/build-pilink.sh`) to
`/tmp/rig` on the Pi, a folder only the admin account can enter. A reboot
clears that, so run it again after one, and after changing code. It needs
`xvfb`, `dosbox`, `xdotool` and `ffmpeg` on the Pi (setup installs any that
are missing) and `~/build/msk316/files/MSK316.EXE` (from `fetch-dos.sh`).

DOSBox uses a whole processor core while it runs, and PAL shares the Pi:
start tests with `nice`, and keep long runs for a quiet lobby.

**Tests**, on the Pi, as the `compaq` user. Screenshots land in `/tmp/rig`.

- `python3 /tmp/rig/program_test.py "guides.py 140588" "[(KEYS, SHOT, SECONDS), ...]"`
  runs a program from `lib/` in the private session.
  - Each step types KEYS at the "Compaq", waits SECONDS, then saves
    `/tmp/rig/SHOT.png` (the 640x400 CGA area).
  - Shots named with "qr" are read with OpenCV's QR reader.
  - PAL's socket is pointed at nothing, so no sound plays in the lobby.
- `python3 /tmp/rig/pal_test.py` runs PAL's photo booth and QR-code tool with
  stand-ins for the camera and voice. The camera frame is a repair photo.
- `RIG_SECONDS=900 python3 /tmp/rig/web_test.py` keeps a private copy of the
  web page up on 127.0.0.1:8099, with a throwaway password in
  `/tmp/rig/webtest/password` that's deleted at the end.
  - Reach it from the Mac with `ssh -N -L 8099:127.0.0.1:8099 pizero`, then
    open http://localhost:8099.
- `python3 /tmp/rig/speed_test.py 9600 38400 ...` times one sixel photo at
  each cable speed (Kermit's settings changed to match).
- `python3 /tmp/rig/apc_test.py` checks that Kermit runs a DOS program when
  the Pi sends it the command (it does with `SET TERMINAL APC UNCHECKED`,
  and refuses with `ON`).
- `python3 /tmp/rig/pilink_rig.py [fifo|nofifo] [rxdelay]` drives PILINK
  alone, straight down its serial port: the hello, a picture checked dot for
  dot against a screenshot, a full screen of random dots at 38400, 57600 and
  115200, the wide-dot sizes, a key going down and up, a command cut short,
  and quitting. `nofifo` makes the serial chip behave like the Compaq's
  16450; `rxdelay` 0 (the default here) makes DOSBox drop any byte the
  program is late for, as the real chip would.
- `python3 /tmp/rig/link_test.py [pilink|kermit] [SIZE]` is the whole
  picture path: a private bridge asks Kermit to run PILINK, shows a photo
  and a QR code, then a moving picture (`link_demo.py`), with keys pressed
  at the "Compaq". `kermit` switches PILINK off (the sixel path). To test
  the "not on the disk" path, rename `/tmp/rig/c/PILINK.COM` first.
- `python3 /tmp/rig/gfx_test.py "PROGRAM" "[STEPS]"` runs any menu program
  the same way, typing at the "Compaq" itself (DOSBox's keyboard), so text
  goes through Kermit and pictures through PILINK. For example
  `gfx_test.py "doomhd.py" "[('wait', 0, 8), ('down', 'Up', 2), ('up', 'Up', 0), ('shot', 'doom', 0)]"`.
  Doom needs `/tmp/rig/doom-frames` (build it as `fetch-net.sh` does, or
  copy `/opt/compaq-net/bin/doom-frames`).
- `python3 /tmp/rig/terminal_test.py [BOOT-IMAGE]` is PILINK as the whole
  terminal: DOSBox runs `PI.BAT` (or, given `boot-freedos-pi.img` copied to
  the Pi, boots the "Compaq" from it), and a private bridge takes PILINK up.
  It checks the text, keys, a picture, PAL's eye in dots, a beep, a file
  sent each way through Kermit as a server, and DOS programs the Pi starts
  (a batch file, then `dos.py play doom` with a pretend Doom), with PILINK
  coming back by itself after each. Shots: `term-*.png`.
- `python3 /tmp/rig/dos_test.py` is PILINK 3's own side of that, with no
  bridge: `PI.BAT` from `C:\PI` as on the Compaq, a file there and not
  there, a batch run and PILINK back with a new hello, and a batch that's
  too long refused. (DOSBox doesn't see files put in its `C:` from outside
  until `RESCAN`; the real Compaq has no such catch.)
- `python3 /tmp/rig/kermit_server_test.py ["BATCH LINE|BATCH LINE"]` runs
  MS-DOS Kermit for one transfer the way `PI.BAT` does (`KERMIT -f
  SERVE.INI`) and has C-Kermit send a file, fetch one and say BYE.

**What the rig can't tell you**
- DOSBox is a CGA machine: it has no 640x400 mode, so pictures there are
  640x200. (The TV stand-in's test, `tools/tests/tv_link_test.py`, shows
  640x400.)
- Its timing isn't a real 286's, and its serial chip forgives more. A speed
  that passes here is a best case for the real Compaq.

**Notes**
- `MSKERMIT.INI` must keep CRLF line endings: DOS Kermit can't read a file
  without them.
- The CGA area of a screenshot is the crop (80, 100, 720, 500); every other
  row is a doubled scan line.
- Move the mouse away first (`xdotool mousemove 799 599`).
- To stop DOSBox: `pkill -f "[d]osbox -conf /tmp/rig"`. The brackets stop it
  from matching its own shell.
