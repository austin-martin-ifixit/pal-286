# Test scripts

Scripts written while building the project. Copy one to the Pi's `/tmp`
(`scp tools/tests/NAME pizero:/tmp/`), then run it as the user its first
comment line names (`desk`, `pal` or root).

Run anything as root or `pal` with `python3 -I` (for example
`sudo python3 -I /tmp/quiz_test.py`). `/tmp` is open to the shared session's
account: without `-I`, Python would load a file someone left there under a
module's name, as root. Tests that need a helper file beside them run as
`desk`, which has nothing to gain.

Some expect a helper file next to them in `/tmp`, or a picture or sound in
the simulator's folders: read the top of the script first. They were written
for the code as it was then, so a failure may mean the test is out of date,
not the code.

**Before testing:** don't type into or restart the live shared session while people may be using it; use a private tmux server (`tmux -L sometest`) and the simulators below.

## The whole lobby in a box: `lobby_sim.sh`

The menu's shared session, the serial bridge, a pretend Compaq running PI
(`lobby_screen.py`: the TV stand-in drawing a 640x400 plasma, saved as
`/tmp/lobbysim/screen/screen.png` every second) and PAL, all in a private
mount namespace on the Pi: there `tmux -L compaq`, `/run/compaq-serial` and
`/run/compaq-pal` are its own, and the shared account's home and
`/var/lib/compaq` are overlays, so nothing shared is touched (notes,
saves, portraits vanish with it). PAL runs at the lobby's pace
(`PAL_SIM_REALTIME=1`): a WAV put in its microphone goes through the same
speech finder as the real microphone, and what it says takes as long as it
would, but lands in a folder: **nothing makes a sound.** It needs a face
in the camera folder to listen. It stops the real PAL (one Whisper at a
time); while it runs, list `compaq-pal` in `/etc/compaq/off` so a deploy
doesn't start the real one (it beeps), and take it out after.

```
bash lobby_sim.sh start                       # on the Pi; then:
bash lobby_sim.sh face face.jpg               # someone at the camera
bash lobby_sim.sh say hello.wav               # 16 kHz mono: `say -o x.wav --data-format=LEI16@16000` on a Mac
bash lobby_sim.sh keys '1\r'                  # typed at the "Compaq" ('\e[21~' is F10)
bash lobby_sim.sh text                        # the shared session's text
bash lobby_sim.sh stop                        # all of it away, and the real PAL back
```

What PAL said is in `/tmp/lobbysim/said/` (`said-NNN.txt`, PAL's files:
read them with sudo) and its log in `/tmp/lobbysim/pal.log`.

## PAL without the lobby: the simulator

`sim_setup.sh` makes `/tmp/pal-sim`, where PAL's camera, microphone and
speaker are folders. `run_sim.sh [fresh]` starts a simulated PAL there, with
its own screen (`sim_screen.py`: the TV stand-in on a pretend display,
behind a private bridge, saved as `/tmp/pal-sim/screen.png` every 2
seconds), so the lobby's screen is left alone. Tests type on that pretend
TV's keyboard by writing to the pipe `/tmp/pal-sim/keyboard` (opened without
O_CREAT: Linux's protected_fifos refuses that on another user's pipe in /tmp). `run_pal_tests.sh` runs the
usual four tests in one go and puts the real PAL back.

It **stops the real PAL** while it runs, so only use it when nobody's in the
lobby. Then:

```
sudo pkill -u pal -f '^python3 -I /opt/compaq/pal/pal.py'
sudo systemctl start compaq-pal
```

Tests that use the simulator:

| Test | What it checks |
|---|---|
| `pal_rehearsal.py` | A spoken rehearsal: greetings, questions, opening programs. **It restarts the real shared screen's program and takes the live bridge's place** (it uses `live-screen/bridge_test3_lib.py`): empty office only, and restart `compaq-tv` (or `compaq-serial`) afterwards |
| `new_behaviors_test.py` | Turn-taking and wake-word behaviour, and the "got it" tick before an answer |
| `consent_test.py` | Spoken consent for learning a face |
| `passerby_test.py` | Shout-outs to people walking past |
| `language_test.py` | Switching languages |
| `quiz_test.py` | The lobby quiz. **It draws on the real TV** |
| `camera_features_test.py` | Mirror, photo booth, "what's wrong with this?" (on the simulator's own screen; shots in `/tmp/tv-*.png`) |
| `music_voice_test.py` | Music by voice. **Real TV and speaker** |
| `fixbot_page_test.py` | "Hey FixBot" through FixBot's own page with the real iFixit login: a repair walked through, the guide panel, the next step, a webcam photo asked about, goodbye. `fixbot_voices.sh` on the Mac first, then `REAL_FIXBOT_PAGE=1 bash run_pal_tests.sh fixbot_page_test.py:pal` |
| `fixbot_menu_test.py` | The menu's FixBot (1 on the main menu): the page on the simulated TV, a question typed with a Backspace, Page Down, and the page gone on leaving. `REAL_FIXBOT_PAGE=1 bash run_pal_tests.sh fixbot_menu_test.py:desk` |
| `fixbot_real_test.py` | "Hey FixBot" against the **real** FixBot (real plans, about a minute each, on the workspace's FixBot plan), a real guide and its photos; screenshots in `/tmp/pal-sim/real-*.png`. `fixbot_voices.sh` on the Mac first, then `REAL_FIXBOT=1 bash run_pal_tests.sh fixbot_real_test.py:pal` |
| `fixbot_sim_test.py` | "Hey FixBot" end to end against a stand-in FixBot on 127.0.0.1:8199 (never the real key or server): words sent word for word, the guide by voice, a step's photo, a question with the step it's on, "we're done", and "Hey PAL" handing a repair over (that part uses Claude). The FixBot lines are the Mac's Daniel voice: run `tools/tests/fixbot_voices.sh` on the Mac first, then `run_pal_tests.sh fixbot_sim_test.py:pal` |
| `regression.sh` | Runs the rehearsal and the quiz in turn |

## No simulator needed

| Test | What it checks |
|---|---|
| `persona_test.py`, `think_test.py` | Claude calls only, as the `pal` user |
| `fixbot_mode_test.py` | FixBot mode's own parts (`pal/fixbot_mode.py`), anywhere with the repo: the wake phrase, the voice commands, an answer read in chunks, the page, and a real guide from FixBot's open guide lookup |
| `qr_tool_test.py` | Whether PAL picks the picture and QR tools; stand-in tools |
| `latency_test.py` | How soon PAL starts talking |
| `music_test.py` | The music module |
| `cookie_test.py`, `web_harden_test.py` | A throwaway copy of the web server on 127.0.0.1:8099, with a throwaway password |
| `pilink_test.py` | The PILINK encoder against PILINK played in Python: every picture size |
| `pilink_repair_test.py` | Lost bytes, repaired: a byte dropped at random inside real frames, PILINK 3's rule for what that spoils played out, and the Pi's repair checked dot for dot (and its cost against sending the whole screen); then the Pi starting a DOS program (RUN) and asking for a file (THERE) |
| `pilink_terminal_test.py` | PILINK as the whole terminal, against PILINK played in Python: the text encoder (changes, scrolling, runs), VT102 text into text-mode cells, and the link taking up a PILINK that started by itself and asking it to leave for a transfer; a mode set on its own, before the screen (the real BIOS is deaf while it sets one) |
| `bridge_hello_test.py` | The serial bridge hearing PILINK's hello whole and in pieces (as the real cable's USB adapter delivers it), and typing that only looks like one |
| `bridge_menu_key_test.py` | F10 reaching the main menu from anything: a picture PAL holds (FixBot's page), a still picture, PAL's own screen, through Kermit; other keys still going to a moving picture's owner |
| `tv_link_test.py` | The TV stand-in playing PILINK, with a pretend display and a private bridge (needs `tools/rig/setup.sh`). With `real` after the layout, a pretend lobby TV showing the Compaq at its own size (`tv-real-*.png`, and F12 pressed twice); with `kermit`, the TV plays a Compaq running Kermit instead of PI |
| `video_rate.py`, `doom_rate.py` | How many frames a second a video or Doom gets through PILINK, against a pretend cable |
| `floppy_test.py` | The Pi Zero's floppy program (`zero/floppy`) with its USB side switched off, in a throwaway folder (needs `tools/rig/setup.sh`) |
| `floppies_test.py` | The menu's floppy-drive code in front of it, with a stand-in for SSH (needs `tools/rig/setup.sh`) |

These two look harmless and aren't: they type into the real shared session.
Empty office only.

| Test | What it does to the live screen |
|---|---|
| `web_flow_test.py` | Its throwaway web server joins the real session and types Enter, 5, 0 into whatever is open |
| `pal_scene_test.py` | Restarts the program on the real screen and takes the live bridge's place (restart `compaq-tv` or `compaq-serial` afterwards) |

## `live-screen/`: these type into the real shared session or the TV

Only run these when the office is empty (after hours). Check the live screen
first: `sudo -u desk tmux -L compaq capture-pane -p -t compaq`.

| Test | What it checks |
|---|---|
| `bridge_test3.py` (+ `_lib`) | The serial bridge, end to end on a fake cable |
| `switch_test.py` | Switching programs by voice |
| `zork_voice_test.py` | Talking to Zork |
| `tip_test.py` | Stuck-player tips |
| `jukebox_test.py` | The jukebox |
| `menukey_test.py` | The main-menu key from inside programs |
| `web_test.py` | Web search |
| `tv_picture_test.py` | Pictures on the real TV |

For screen and picture work, prefer the virtual Compaq in `tools/rig/`,
which touches nothing live.
