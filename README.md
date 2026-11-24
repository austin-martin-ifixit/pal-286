# PAL 286: a 1987 Compaq Portable III, revived with a Raspberry Pi

This is the code behind PAL 286, the Compaq Portable III in the lobby of
iFixit's Chattanooga office. The whole story, with photos and videos, is on
iFixit: https://www.ifixit.com/Wiki/PAL_286

A Raspberry Pi 3 B+ does the thinking, and the Compaq is its screen and
keyboard over a serial cable. What's in here:

- `dos/pilink.asm`: PILINK, the 2,949-byte DOS program that takes pictures
  from the Pi straight into the Compaq's screen memory and reports every key
  going down and coming back up.
- `pi/opt/compaq/`: everything that runs on the Pi. The menu, the serial
  bridge, PAL (camera, speech recognition, Claude, the robot voice),
  PotatoTube, the games and the shared web view.
- `emulator/` and `tools/rig/`: the virtual Compaq the software was built and
  tested on before the real one worked.
- `docs/`: the research on getting data into a 1987 computer, and the graphics
  measurements.

Heads-up: this is a snapshot of a one-machine hobby project, shared as is.
It's written for this exact Compaq, Pi and office (the manual below is the
working one), so expect to change paths, devices and settings. The Claude and
FixBot keys are typed into setup scripts at install time; none are stored
here. Most of the code was written by Claude, working with me; FixBot helped
bring the hardware back to life.

License: MIT (see `LICENSE`), except the bundled font and xterm.js in the
`vendor/` folders, which keep their own licenses.

---

# The working manual

Turns a Raspberry Pi 3 Model B+ into the brains of a Compaq Portable III. The
two are joined by a serial cable:

    Pi (USB port) -> FTDI USB serial adapter -> null modem cable -> Compaq COM1

The same SD card also runs on the Pi Zero W it started on (plug the serial
adapter in through a micro-USB OTG adapter there), but the Zero's 2.4 GHz-only
Wi-Fi was far too slow on the crowded office network.

**Wi-Fi:** the B+ joins the office Wi-Fi on 5 GHz. Its built-in Wi-Fi chip is
unreliable (it failed to load its firmware on several boots), so a TP-Link
Archer T2U Nano USB adapter (RTL8811AU, `rtw88_8821au` driver) is plugged in
as well. The office network isn't tied to either radio, so whichever
starts gets used; tested by switching the built-in one off. If the card ever
goes back into the Zero, clear the 5 GHz lock first:
`nmcli connection modify "<your Wi-Fi>" 802-11-wireless.band ""`.

The Compaq runs MS-DOS Kermit as a terminal onto one **shared session** on
the Pi: the Compaq menu (FixBot, iFixit repair guides, Office, Internet, Games,
the Linux command line, file transfer, Pi status and shutdown). Everyone on the
office network can open the same session at **http://compaq.local** with the
office password, watching the Compaq's screen live and typing into it.

    Compaq (Kermit) --cable--> serial bridge --\
    browsers at http://compaq.local -----------+--> one tmux session: the menu
    Virtual Compaq on the Mac (SSH) -----------/      (limited "desk" account)

Kermit is a terminal: it shows text, and draws pictures slowly. For
pictures the Pi asks Kermit to step aside for **PILINK**, a small program of
ours on the same disk, which takes them straight off the cable at up to
115200 baud and tells the Pi when each key goes down and comes up (see
"Pictures on a 1987 screen").

The shared session runs as `desk`, an account with no password, no SSH, no
cron jobs, no `su` and no admin rights (except shutting the Pi down), so
nothing typed on the Compaq or the web can take over the Pi. It can't read
the Claude or FixBot keys (PAL's service holds both and makes FixBot
requests for the menu), and its shell start-up files are reset whenever the
session starts. Changing the office password signs everyone out and restarts
the session. Admin work happens over SSH as `compaq`.

**Getting around:** F10 (or Ctrl-\\) in any program, on any screen, goes
straight back to the main menu, closing the program (save first). On the
Compaq, Kermit sends it for F10; on the web page it's the "Main menu"
button; out loud it's "Hey PAL, go to the main menu" (unless someone has
typed from a browser in the last 30 seconds: they can't hear the lobby).

## Quick reference

| To... | Do this |
|---|---|
| Use the Compaq from a laptop or phone | http://compaq.local, then the office password |
| Get back to the main menu | F10 (or Ctrl-\\) anywhere; the web page's "Main menu" button; or "Hey PAL, go to the main menu" |
| Talk to PAL | Stand in front of the webcam and say "Hey PAL, ..." |
| Quiet PAL for a while | "Hey PAL, quiet for an hour", or menu: PAL 286, Quiet mode |
| Check that everything's healthy | `./check.sh` |
| Install changes made in this folder | `./deploy.sh` |
| Back up the Pi (no password needed) | `./backup.sh` |
| Change PAL's settings | `ssh -t pizero 'sudo nano /etc/compaq/pal.conf'`, then `ssh pizero 'sudo systemctl restart compaq-pal'` |
| See what PAL has been doing | `ssh pizero 'journalctl -u compaq-pal -n 50'` |
| Add a Wi-Fi network | `./add-wifi.sh "Network name"` (it asks for the password) |
| Switch a part off for good (PAL, the TV, the web page) | Put its name (`compaq-pal`, `compaq-tv`, `compaq-web`) on a line in `/etc/compaq/off` on the Pi, then `./deploy.sh` |
| Move to a new SD card | See "Moving to a new SD card" below |
| See the Compaq's web page from outside the office | `ssh -N -L 8080:localhost:80 pizero`, then open http://localhost:8080 |
| Go back to slow pictures (if the fast ones misbehave) | `ssh pizero 'sudo touch /etc/compaq/no-pilink; sudo systemctl try-restart compaq-tv compaq-serial'`. Remove the file and restart again to undo |
| Change the cable's speed | Put the speed in `pi/opt/compaq/data/cable-speed`, then `./deploy.sh` and `./make-disks.sh` (see "When the hardware arrives") |

## What's on the menu

- **Ask FixBot**, **iFixit repair guides** (a step at a time, with each
  step's photos on the screen and a QR code to carry on on a phone), the
  **office message board**
- **PAL 286:** talk to PAL, the Jukebox, the photo-booth gallery, teach PAL
  your face or make it forget you, quiet mode, status, and how PAL works
- **Office:** WordGrinder, sc spreadsheet, calcurse, qalc, Midnight Commander,
  a dictionary (English, FOLDOC and the Jargon File), a shared repair job
  queue (Taskwarrior) and a typing tutor (gtypist)
- **Internet:** web search, PotatoTube, Lynx, Wikipedia, text news sites,
  weather, IRC, BBSes, news feeds (newsboat: iFixit, Hackaday, Hacker News,
  Lobsters, Ars Technica, 404 Media) and Gopher/Gemini (Bombadillo)
- **Games:** DOOM (run by the Pi; in real dots with PILINK, in text without), DUSTRUN (original, below), Zork I-III and more text
  adventures, NetHack, Moria, GNU Chess, 21 BSD games, and more (Tetris,
  2048, Minesweeper, Moon Buggy, GNU Go, Greed, Sudoku,
  robotfindskitten, typespeed; tty-solitaire is installed but left out: it
  needs a 57x28 screen). Doom starts straight in the first level
- The Linux command line, Kermit file transfer, Pi status, shut down (it
  asks for the word OFF: one stray "y" from a visitor would leave the lobby
  dark until someone unplugs the Pi)

The welcome screen shows a computing fortune (or a BOFH excuse), and the main
menu's header shows how many browsers are watching at compaq.local.

**DUSTRUN** (`lib/dustrun.py`) is an original turn-based game written for this
screen: harvest crystals on the salt flats and haul them to base while
burrowers, which hunt by sound and can't cross rock, close in. Five in-game
days; the office shares one high-score table in `compaq-files/saves`. It
redraws only what changed: about 2.3 KB to start, then roughly 66 bytes a move.

## The modern web, squashed into 1987

The Pi does the real browsing; the Compaq gets whatever survives the trip.

- **Web search** (Internet menu, or "Hey PAL, search for ..."): ten results
  from DuckDuckGo's page for text-only browsers (Google has no search service
  a program like this may use: its API is closed to newcomers and ends in
  January 2027, and its pages turn robots away). PAL types the search in
  when you ask it. A number reads that page in Lynx; P and a number (P1)
  paints the real page, as Chromium on the Pi draws it in an 800-pixel
  window, onto the Compaq a screenful at a time in dithered amber dots
  (headlines and photos survive; body text mostly doesn't, which is the
  point); L and a number (L1) shows a QR code to open it on a phone. If
  DuckDuckGo ever answers with a robot check, it's left alone and PAL's own
  web search (Claude) fills in.
- **PotatoTube** (Internet menu, or "Hey PAL, play ... on YouTube"):
  YouTube in the worst quality ever offered. The Pi fetches the smallest
  version there is (144p, about 80 kbit/s; yt-dlp, with QuickJS answering
  YouTube's JavaScript check), turns each frame into amber text art (4
  frames a second on the TV and in browsers, 1 a second over the real
  Compaq's 9600-baud cable) and PAL plays the sound on the lobby speaker
  (not during quiet hours). Videos up to 10 minutes; about half a minute to
  fetch, while its thumbnail paints on the screen as a real picture. Over
  the cable it skips frames the cable can't carry, so the picture keeps up
  with the sound. At the end, L shows a QR code to watch it properly on a
  phone. When YouTube changes and it stops working: `./fetch-net.sh --latest`.
- **PotatoTube HD:** the same potato in real dots. Pick a video and it asks
  "C: characters" (the text art, and what Enter picks) or "H: HD". `H1` or
  `C1` at the list skips the question, and "Hey PAL, play ... on YouTube in
  HD" goes straight to HD. Each frame becomes 320x200 amber dots and goes
  through PILINK, which only carries what changed: about 9 frames a second
  for calm scenes and 6 for busy ones at 115200 baud (measured against the
  real encoder with a test film; 7.2 on the TV). On a slower cable it halves
  the rows to keep moving. When this Compaq has no PILINK it doesn't ask,
  and plays the text version.
- **DOOM** (Games menu, or "Hey PAL, open Doom"): on the real Compaq with
  PILINK 3, the 286 runs Doom8088 itself (next item), because the cable
  can't carry many pictures a second; the Pi puts it on the hard disk from
  the Doom floppies the first time, and F10 in the game comes back to the
  menu. Anywhere else (the TV, an older PILINK), real Doom (the shareware
  first episode) running on the Pi. With PILINK it's drawn in real dots,
  5 to 7 pictures a second at 320x100 (the key under Esc swaps to a sharper
  320x200 at 3 to 4), and keys at the Compaq can be held: walk, turn and
  fire like 1993. Without PILINK it's doom-ascii, drawn 70x22 in text, with
  keys as taps (a terminal can't tell when a key is let go) and about a
  frame a second over the cable. No sound either way: the speaker is PAL's.
- **Native DOOM on the 286:** Doom8088 (a port for 16-bit PCs) on two
  floppies, `doom8088-disk1/2.img`. The menu's Doom installs and starts it
  (`lib/dos.py`, below); by hand, `A:INSTALL` puts it on the hard disk (the
  game data is too big for one floppy), then `DOOM` plays it in crisp
  640x200, or `DOOMCGA` in four shades of amber, with PC speaker sound.

## Pictures on a 1987 screen

The Compaq shows real pictures, not just text: two colours, amber and dark,
so photos are dithered. A program asks the serial bridge for a picture
(`pictures.show()`); the bridge takes the screen over, paints it, and gives
the screen back on a key there (it tells the program which key, so Q can
stop a run of pictures) or when the program lets go. How it paints depends
on what the Compaq has.

**With PILINK (the fast way).** `PILINK.COM` is a 2.6 KB DOS program of ours
(`dos/pilink.asm`) on the Kermit disk. When a picture is wanted, the bridge
sends Kermit a command to run it (`SET TERMINAL APC UNCHECKED` in
`MSKERMIT.INI` allows that). PILINK then:

- reads the serial port itself, and the two ends find the fastest speed
  that passes a test: 115200 baud if the Compaq keeps up, else 57600 or
  38400;
- puts what arrives straight into video memory. The Pi remembers what the
  screen shows and sends only what changed;
- uses every dot the plasma has, 640x400, when the Compaq's BIOS accepts
  that mode, else the CGA's 640x200;
- reports each key going down and coming up, which no terminal can.

When the picture comes down, PILINK quits and Kermit carries on. A photo
takes a second or two. Programs can also hold a canvas and send screenful
after screenful (`pictures.Canvas`): that's PotatoTube HD and Doom.

**PILINK as the whole terminal (`PI` at the DOS prompt).** `PI.BAT` on the
Kermit disk runs PILINK by itself, with no Kermit. The bridge takes it up
when it says hello, and from then on sends the shared screen's text
straight into the Compaq's own text mode as well as the pictures:

- text at whatever speed the cable passes (115200 if the Compaq keeps up),
  not Kermit's 9600: only the characters that changed go, a byte each, and
  a scroll moves the screen instead of sending it again (a full screen of
  text is about 1.8 KB, a line scrolling in about 80 bytes);
- pictures with no 2-second handover, and keys held and released at any
  time;
- PAL's eye in real dots (below), and the Compaq's own speaker;
- file transfers still use Kermit: PILINK goes back to DOS with a code that
  makes `PI.BAT` run Kermit as a server (`SERVE.INI`), the Pi sends or
  fetches the files, and Kermit's goodbye brings PILINK straight back.
  "Receive files" then asks for DOS file names (like `*.TXT`) instead of
  asking someone to type SEND at the Compaq;
- no need for DOS's `COMMAND.COM` to be findable (Kermit's RUN needed it);
- DOS programs the Pi starts (PILINK 3, `lib/dos.py`): the Pi sends a batch
  file, PILINK writes it as `C:\PI\PIRUN.BAT` and goes to DOS with exit
  code 12, `PI.BAT` runs it, and its last lines (`C:`, `CD \PI`, `PI`)
  bring PILINK back, so the menu carries on when the program ends. The
  Pi can also ask whether a file is on the Compaq's disks, which is how
  it knows to install a game first (from its floppies, which the Pi Zero
  puts in the GoTEK). A program on the 286 draws as fast as the 286 can,
  where the Pi's pictures wait on the cable. The bridge takes
  `{"op": "run"}` and `{"op": "there"}`;
- lost bytes cost little (PILINK 3): PILINK checks for a loss before it
  acts on any count or address, so only what the frame on its way changed
  can be wrong, and the Pi sends just that again. Before, the Pi set the
  mode again (a blank screen) and sent the whole screen: 8 seconds at
  640x400 over a 38400 cable, which is the likeliest reason PotatoTube
  crawled on the real Compaq. The bridge logs each loss's reason (the
  serial chip's overrun, a command stopped halfway, and so on), and
  `/run/compaq-serial/pilink` counts them.

Ctrl+Alt+Esc leaves for the DOS prompt; `PI` goes back, `KERMIT` is the old
way in and still works (the first key typed at Kermit tells the bridge).
`/run/compaq-serial/terminal` says which one the Compaq uses. Tested on the
virtual Compaq (`tools/rig/terminal_test.py`), not yet on the real one.

Measured on the virtual Compaq (the real Kermit and the real PILINK in
DOSBox, at about a 286's speed), not yet on the real machine:

| | Through Kermit at 9600 | Through PILINK at 115200 |
|---|---|---|
| A repair photo | 9.6 s | 0.9 s |
| A QR code | 1.7 s | 0.7 s |
| A full screen of random dots (the worst case) | can't keep up past 38400 | 1.3 s |

**Without PILINK (the slow way).** If the disk has no PILINK (or it doesn't
answer, twice), Kermit draws the picture itself: Tektronix graphics, with
DEC sixel images inside, dot for dot on the CGA's 640x200. It paints from
the top down at the cable's speed, like an old bulletin board (a
full-screen photo is about 10 KB: ten seconds at 9600 baud). Moving
pictures need PILINK; programs fall back to text.

`./check.sh` says which way pictures are going, and at what speed.

- **iFixit guides:** P paints the step's photos, L a QR code for that step.
- **Web search:** P1 paints the page, L1 a QR code for it.
- **PotatoTube:** the thumbnail while it loads, and a QR code after.
- **PAL:** the photo booth paints a real photo (the gallery still keeps only
  a text-art version, never the photo), and "send it to my phone" puts up a
  QR code for a link PAL knows (a guide, an ifixit.com page). With PILINK as
  the terminal, PAL is drawn in real dots (`pal_screen.dots`): a round eye
  whose centre pulses while PAL listens, with its words in the Compaq's
  font; the quiz board in big lettering; the jukebox's keyboard as a real
  piano, keys going down as they play; and the mirror as a moving dithered
  picture of the camera, not text art. (PAL sends each board's rows of text
  for Kermit, and beside them what the board means, which the bridge draws.)
- **Browsers** at compaq.local see the same dots over their screen while a
  picture is up (`/run/compaq-serial/picture.png`, served only to signed-in
  browsers), and a key there goes on too. PAL's photo-booth pictures are the
  exception: like PAL's scenes, only the lobby sees them.
- **The TV** standing in for the Compaq plays both ways too: it mimics
  Kermit's graphics quirks dot for dot, and it plays PILINK (the same bytes
  into the same video memory, 640x400), at the pace a 115200-baud cable
  would set, so what the TV shows is what the Compaq should.

Sixel quirks in Kermit, found by testing the real program in DOSBox: the first band
of an image is drawn 8 dots above the graphics cursor (so the cursor is
moved first), later bands always start at the left edge (so pictures are
placed by padding), the last band is dropped (so a blank one goes last), and
sixel aspect settings are ignored. Details in the comments at the top of
`pictures.py`.

## Looking after the plasma screen

The Portable III's gas-plasma panel is prone to burn-in, so nothing static
stays on it: the bridge (`serial_bridge.py`) shows a small clock that moves
every minute after 15 minutes with no key at the Compaq and no change on
screen, Kermit's status line is turned off (`set mode-line off`), and tmux
has no status bar. A key at the Compaq wakes it (the key is swallowed so it
can't pick a menu item), and so does a change someone typed in a browser.
A program redrawing a clock by itself doesn't wake it. Browsers never see
the saver. Turning the Compaq off overnight helps too.

## PAL 286, the lobby greeter

PAL is the lobby computer's voice: a friendly, quick-witted 1987 computer
and a good host, in plain words anyone can follow (since 2026-11-02; it was
a Gen Z-slang wise guy before, which came out awkward through a speech
synthesizer), with the odd deadpan HAL moment for contrast, and Claude
doing the thinking. Visitors are told they can just say "Hey PAL". It
jokes about itself (640 K, the plasma, the carry handle), the lobby and
modern life, and is told everything it has said today so it doesn't repeat
a joke.

- **Greets people** who walk up to the webcam: by name if they've taught it
  their face, otherwise as an "unidentified human". Once every 4 hours per
  person; one greeting for a stream of visitors. **Shout-outs** for people
  who just walk past (a short burst of movement, not a face): at most one
  every 20 to 30 minutes, 3 an hour and 15 a day, and less often while
  nobody stops (`PASSERBY=no` or `PASSERBY_MINUTES` in `pal.conf`). Claude
  writes them eight at a time, so they're instant and fresh.
- **Talks back, when asked.** "Hey PAL" starts a conversation (a pause
  after "Hey PAL" is fine). After each answer PAL keeps listening 7
  seconds in case you carry on (12 if it asked a question, with a rising
  "your turn" blip from the Compaq's own speaker when PI is running);
  after that, say "Hey PAL" again (within half a minute it remembers what
  was just said). Chatter in those seconds that isn't for PAL gets no
  answer (Claude says SKIP). PAL can't hear while it talks, so an answer
  started over its last words is lost. Its log notes how long each answer
  took: it starts answering 5 to 6 seconds after you stop talking (1 s to
  be sure you've finished, 2 to 3 s for Whisper, about 1.5 s for Claude's
  first sentence); while Whisper works, the camera rests. It knows a lot,
  looks up current things on the web (with a dial-up modem sound), and
  knows the time, the weather, the message board, and roughly how busy the
  lobby has been (people walking past, quiet spells: counts only).
- **Remembers.** Short notes about each person who taught it their face
  (what they're working on, running jokes), and birthdays they tell it
  (it sings Happy Birthday when it first sees them on their own on the
  day). Notes about the office are general, never about a named person or
  anything confidential, and are only kept from chats with someone PAL
  knows, so a passing visitor can't plant "facts" for it to repeat
  (`NOTES_FROM_VISITORS=yes` in `pal.conf` keeps them from anyone's chat).
- **Plays music:** "Hey PAL, play some music", "play the Entertainer",
  "write me a song about Mondays", "sing Daisy Bell", "sing happy birthday
  to Sam". 21 public-domain tunes as 1980s chiptunes (pulse waves, triangle
  bass, noise drums, like a NES), tunes Claude composes on the spot, and
  singing in the style of the IBM 7094 that sang Daisy Bell in 1961. The
  plasma shows a now-playing card with the notes lighting up over a
  keyboard; a key at the Compaq stops it. Asked out loud, tunes stop at 30
  seconds with a fade; `MUSIC_VOLUME` (0 to 1, default 0.5) sets how loud. Menu: PAL 286, Jukebox, where the
  notes fall down the screen onto a keyboard as they play.
- **Hosts a quiz** on anything ("Hey PAL, quiz me about space"): three
  questions a round, each on the plasma screen with its choices and the
  score (say the letter or the answer), a final score with a title, and
  today's best score to beat.
- **Speaks other languages** when asked ("Hey PAL, can you speak Spanish?"):
  its voice, its replies and its hearing switch for that conversation.
  Spanish and Italian come through well; others more roughly (the Pi 3 can
  only run Whisper's smallest model, told which language to expect, since
  left to guess it guesses wrong).
- **Camera tricks:** "show me the mirror" (the camera as live text art for
  half a minute), "take my picture" (a countdown, then a real photo painted
  in amber dots; "save it" keeps a text-art version in PAL 286, Photo booth
  gallery, never the photo), "send it to my phone" (a QR code for the guide
  or page being talked about), and "what's wrong
  with this?" while holding up a phone or part (Claude looks at one photo
  of the thing, then can find the iFixit guide or start FixBot). Once
  FixBot has its key, repairs are FixBot's alone: see "Hey FixBot" below.
- **"Hey FixBot"** hands the conversation to FixBot by voice, for a whole
  repair (below, under FixBot).
- **Knows what's open on the Compaq** (it's told in every conversation, so
  it doesn't offer to open what's already open, and asking for an open
  program leaves it as it is), and **knows iFixit**: its story, tools,
  teardowns, FixBot and right to repair, from the office notes file.
- **Opens programs on the Compaq** when asked ("Hey PAL, open DUSTRUN",
  "Hey PAL, go to the main menu", "show me how to fix an iPhone 12
  battery"): the ones in `data/voice-apps`, guides and FixBot, switching
  straight from whatever is open (closing it, as F10 does). It leaves the
  screen alone only while someone is typing from a browser.
- **Plays along.** In a text adventure at the lobby keyboard, say the move
  ("open the mailbox", "take the paper thing") and PAL types it (it says so
  when the game starts, and only listens while someone is in view). It reacts
  when the player dies, wins or scores (also in DUSTRUN and NetHack), and
  if a program keeps saying it didn't understand, PAL suggests what to type.
  At most one tip every two and a half minutes; `TIPS=no` turns tips off.
- **Shows up on the plasma screen** (a glowing eye, the conversation typed
  out in time with the voice). When PAL starts talking by itself (a
  greeting, a shout-out) it shows only if nobody has typed anywhere for 2
  minutes. When someone says "Hey PAL" it shows unless someone typed on
  the web in the last 30 seconds: the person at the lobby keyboard is the
  one talking. A key at the Compaq gives the screen straight back. The
  bridge's log says why whenever it holds the eye back
  (`journalctl -u compaq-serial | grep "pal:"`).
- **Typed chat** too: menu, PAL 286, Talk to PAL.

Hardware: a USB webcam with a microphone (a Logitech C920 works) and
powered speakers in the Pi's headphone socket (or a USB speaker). Everything
is found automatically; `./check.sh` shows what PAL sees.

Speech runs on the Pi: Whisper (tiny English model, whisper.cpp built with
the Pi 3's NEON maths) turns speech into text in about two seconds, and
espeak-ng plus sox make the voice. Faces: OpenCV's YuNet finds them and
SFace turns each into 128 numbers. Only Claude's part goes over the
internet: the text of the conversation (and, when someone asks PAL to look
at something, one camera picture), never sound.

**Privacy, by design.** PAL recognizes only people who chose to teach it
their face at the menu (PAL 286, Teach PAL your face) and said "yes" out
loud at the camera when it asked, so nobody can enroll someone else from a
browser. (A clear "yes", "yeah" or "go ahead": not "okay", which the speech
engine sometimes hears in a cough. Nothing else plays through the speaker
while PAL waits for it.) It keeps their name, 128 numbers per face (not a photo) and short
notes, in `/var/lib/compaq-pal`, readable only by PAL's own account; it
uses someone's notes only while they're the one face in view (if someone
else walks up, the conversation starts afresh without them). Anyone can
make it forget them: the menu (then say "forget me" at the camera) or by
asking it (that deletes their face, notes and birthday). No video or
recordings are kept, photo-booth portraits only when someone asks (as text
art, visible in the menu's gallery), typed chats with PAL aren't saved, and
the logs record counts, not names or what was said. A visitor's face
signature stays in memory (never on disk) for half an hour so they're
greeted once. Between conversations it listens only for its name, and only
while someone is in front of the camera, or while someone plays a text
adventure at the lobby keyboard (to type their moves). Movement is only
counted (for shout-outs and "busy today"), never recorded. Only PAL's
account can reach its speech engine (a firewall rule loaded with the
service). Put up a small sign: "The lobby computer has a camera and
microphone (menu: PAL 286)." Some
places have laws about face recognition (Illinois, Texas and Washington,
for example); opt-in and forget-me cover the usual requirements, but check
if you're in one.

Costs: each greeting or answer is one small Claude request, billed to the
key's account, plus $10 per 1,000 web searches (PAL searches only for live
news, scores and the like). The Claude Console shows the running total.
`MODEL` is Sonnet 5.5, the quickest to start talking (about 1.7 s); Opus
5.5 is a little cleverer but takes 2.5 to 4 s; Haiku 5.5 is cheapest. Each
runs with little or no thinking first, since banter doesn't need it.

Settings are in `/etc/compaq/pal.conf` (name, model, voice, volume, quiet
hours, how often to greet, tips, passer-by shout-outs, devices, and `CITY`
for the weather), and what PAL knows about the office in
`/etc/compaq/pal-office.txt` (read at every conversation). Deploys never
overwrite either; new settings are added to the end of `pal.conf`. Edit
with `ssh -t pizero 'sudo nano /etc/compaq/pal.conf'`, then
`ssh pizero 'sudo systemctl restart compaq-pal'`. Voices: `mainframe`
(calm, the default), `clear` (the same at a normal talking pace),
`dectalk` (1980s terminal) or `arcade` (8-bit robot); samples are in
a folder of voice samples outside this repository.

**Character voices.** "Hey PAL, talk like an ogre" (or a movie-trailer
narrator, a space villain, a chipmunk, a posh butler, a 1940s radio
announcer, a grandpa, a spooky whisper) changes PAL's voice for that
conversation; it goes back to its own a little after (`change_voice`, like
`speak_language`). The menu's PAL 286, then "Change PAL's voice", picks one
for an hour. They're espeak voices and accents with sox effects
(`senses.Voice.STYLES`, with their own pace in `PACE`), not copies of
anyone's voice: asked to sound like a real person, PAL says it can't.

## The Compaq's screen on a TV (until the Compaq is connected)

With a TV or monitor on the Pi's HDMI port, `compaq-tv.service` makes it the
Compaq: the shared session in the Compaq Portable III's own font, amber on
dark like the plasma panel, with a keyboard plugged into the Pi as the
Compaq's keyboard. It plays a Compaq running `PI` (`TERMINAL=pi` in
`pi/opt/compaq/data/tv.conf`): PILINK is its whole terminal, so the text,
the pictures and PAL's eye and boards in real dots arrive exactly as they
will on the Compaq with PI. `TERMINAL=kermit` plays one running Kermit
instead (pictures through PILINK, everything else as a VT102).

How big it draws is set in `pi/opt/compaq/data/tv.conf` (then
`./deploy.sh`):

- `real` (the setting now): the Compaq's own size, its 10-inch panel, in the
  middle of the TV, so you see what people at the Compaq will see. On the
  lobby's Samsung (UN32EH4003F, 31.5 inches) that's 421 by 265 TV pixels
  for the Compaq's 640 by 400 dots: the TV's pixels are coarser, so dots
  are blended (dithered pictures look as they do from a step back) and
  small text is softer than the plasma's.
- `dot`: one TV pixel per dot, sharp, about one and a half times the real
  size on that TV.
- `fill`: as big as the TV allows, sharp (twice that again).

**F12** on the TV's keyboard switches between filling the TV and the
Compaq's real size, whenever you like (the key never reaches the Compaq's
programs; the setting comes back after a restart). A different TV needs its
picture width in `TV_WIDTH_MM` (TVs don't report it: this one claims to be
160 mm wide). It runs the same
serial bridge as the real cable (on a pseudo-terminal), so the screen saver
and PAL's eye appear on it too, and PAL can talk through the TV's speakers
(`SPEAKER=plughw:CARD=vc4hdmi,DEV=0` in `pal.conf`).

It uses console 7; Ctrl+Alt+F1 reaches the Pi's login prompt, Alt+F7 comes
back. Plugging in the Compaq's serial adapter stops it and hands over to the
real Compaq; unplugging it brings the TV back. File transfers need the real
Compaq. Ctrl+Alt+Del and the SysRq keys can't reboot the Pi from a lobby
keyboard. To turn it off for good: `ssh pizero 'sudo systemctl disable
--now compaq-tv'`.

## Virtual Compaq (preview on the Mac)

Double-click `Virtual Compaq.command` in the folder above this one. It opens a
browser window styled like the Portable III's amber plasma screen, in the
Compaq's own BIOS font, connected live to the Pi. Type `KERMIT` at the `A>`
prompt, just as on the real machine. `Ctrl-]` then `C` reaches the Kermit
prompt (`CONNECT`, `EXIT`, `STATUS`); `Ctrl-]` twice sends one to the Pi. The
cable speed switch shows output at the real 9600 baud or instantly.

It's `emulator/server.py` (Python standard library only) and
`emulator/index.html`, with xterm.js and the Compaq Port3 font in
`emulator/vendor`. Each Kermit connection joins the shared session over SSH,
so it shows the same screen as the Compaq and http://compaq.local.

## Scripts (run on the Mac, from this folder)

| Script | What it does |
|---|---|
| `./deploy.sh` | Installs everything under `pi/` on the Pi. Replaces `/opt/compaq`, so edit here, not on the Pi |
| `ssh pizero 'sudo bash -s' < fetch-games.sh` | Downloads Zork I-III and the free text adventures to `/var/lib/compaq/games` |
| `ssh pizero 'bash -s' < fetch-dos.sh` | Downloads MS-DOS Kermit, FreeDOS 1.3's floppy edition (for the boot disk) and the free DOS classics for the Compaq's disks to `~/build` (checksums verified) |
| `./make-disks.sh` | Builds every Compaq floppy image into `disks/1200k` (1.2 MB; see below). Run `fetch-dos.sh` first |
| `tools/build-pilink.sh` | Assembles `dos/pilink.asm` into `pi/opt/compaq/dos/PILINK.COM` (with nasm, on the Pi). Only after changing PILINK; then `./make-disks.sh` and `./deploy.sh` |
| `./set-office-password.sh` | Asks for the office password for http://compaq.local; the Pi keeps only a hash. Changing it signs everyone out |
| `./set-fixbot-key.sh` | Asks for a FixBot API key, checks FixBot accepts it, and saves it on the Pi, readable only by PAL's service |
| `./set-ifixit-login.sh` | Asks for the `session` cookie of a logged-in iFixit account (the script says how to copy it), checks it with iFixit (which says whose it is) and saves it on the Pi, readable only by PAL's service: FixBot's own page then runs logged in |
| `./add-wifi.sh "Network"` | Asks for a Wi-Fi password and saves the network on the Pi (any radio, 5 GHz or 2.4) |
| `./check.sh` | Health check: temperature, power, storage, Wi-Fi band and latency, services, serial adapter, password and key, updates, and the web page |
| `./set-claude-key.sh` | Asks for a Claude API key for PAL, checks Anthropic accepts it, and saves it on the Pi, readable only by PAL |
| `./fetch-pal.sh` | Downloads PAL's face and speech models (checksums verified) and builds Whisper on the Pi (about 15 minutes, once) |
| `./fetch-net.sh [--latest]` | Sets up yt-dlp for PotatoTube (pinned and checksummed; `--latest` for YouTube's newest changes) and builds Doom twice: doom-ascii (text) and doom-frames (for real dots) |
| `./setup-backup-key.sh` | Once: makes the backup key, locked with a password you choose (never stored) |
| `./backup.sh` | Backs up everything that lives only on the Pi (settings and keys, PAL's memory, the shared files, Wi-Fi networks, the Pi's SSH identity, the Whisper build) into one encrypted file in `backups/<date>/`; needs no password |
| `./restore.sh backups/<date>` | Puts a backup onto a Pi (a fresh card, after `deploy.sh`); asks for the backup password |

The Pi is `pizero` in `~/.ssh/config`, reached as `compaq.local`, so the same
shortcut works on any network the Pi joins.

## On the Pi

| Path | What it does |
|---|---|
| `compaq-desk.service` | The shared session: tmux (`/opt/compaq/tmux.conf`) running `/opt/compaq/session` as `desk`, 80x24, plain ASCII, idle sign-off after 30 minutes |
| `compaq-serial.service` | `lib/serial_bridge.py`: joins the cable (8N1, no flow control, at the speed in `data/cable-speed`) to the shared session, repaints the Compaq when Kermit opens its port, runs the burn-in saver, shows pictures (through PILINK when the Compaq has it), and runs Kermit on the cable for transfers (Ctrl-C cancels one). Started by the udev rule |
| `compaq-web.service` | `web/server.py` on port 80: the shared session in the browser, behind the office password |
| `/etc/udev/rules.d/99-compaq-serial.rules` | Names any USB serial adapter `/dev/compaq`, starts the bridge, and tells an FTDI adapter to pass bytes on at once (PILINK's keys and answers) |
| `/opt/compaq/data/cable-speed` | The cable's everyday speed, Kermit's (9600 to start with). The one place it's set: the bridge reads it, and `make-disks.sh` writes it into the Compaq's `MSKERMIT.INI` |
| `/opt/compaq/dos/PILINK.COM` | The Compaq's fast picture program, as built (`dos/pilink.asm` is its source, and describes what the two ends say to each other) |
| `/opt/compaq/lib/pilink.py` | The Pi's side of PILINK: the screen layouts (text mode too), the encoders that send only what changed, the session (start, find the speed, show, keys, stop, or take up a PILINK that started by itself as the terminal), and PILINK played in Python for the TV and the tests |
| `/opt/compaq/lib/text_screen.py` | The shared screen as the Compaq's text mode holds it, for when PILINK is the terminal (a VT102 emulator, pyte, turned into code page 437 cells) |
| `/run/compaq-serial/terminal` | `pilink` or `kermit`: which terminal the Compaq runs, so a restarted bridge doesn't type text at a PILINK that's waiting for it |
| `/etc/sudoers.d/020_compaq-desk` | Lets `desk` run `systemctl poweroff`, nothing else |
| `/opt/compaq/session` | The welcome screen, then the menu, round and round |
| `/opt/compaq/menu` | The menu. Lists `apps/`; subfolders are sections named by their `.title` |
| `/opt/compaq/apps/` | One executable per menu item. Its `# title:` line is the menu text; the number prefix sets the order |
| `/opt/compaq/lib/chat.py` | Chat sized for 80x24 at 9600 baud; FixBot and Echo backends |
| `/opt/compaq/lib/ifixit.py` | FixBot Partner API client: plans, search, guides |
| `/opt/compaq/lib/guides.py` | Search and read iFixit guides, a step at a time with photos (no key needed) |
| `/opt/compaq/lib/pictures.py` | What programs call for pictures: `show()` for a still one, `Canvas` for a moving one, `Dots` to turn film frames into dots, QR codes, and the sixel fallback |
| `/opt/compaq/lib/websearch.py`, `snapshot.py`, `potato.py` | Web search, web pages as pictures, PotatoTube (text art, and HD in dots) |
| `/opt/compaq/lib/doomhd.py`, `/opt/compaq-net/bin/doom-frames` | Doom in real dots: the game (built by `fetch-net.sh` from `tools/doomgeneric_frames.c`) and the program that passes its frames to the Compaq and the Compaq's keys to it |
| `/opt/compaq/lib/asciify.py` | Wraps programs that draw with Unicode (WordGrinder) so the Compaq can show them |
| `/opt/compaq/lib/weather.py` | Weather from wttr.in |
| `/opt/compaq/lib/transfer.py` | Asks the bridge for a Kermit send or receive (used by "Transfer files") |
| `/opt/compaq/lib/floppies.py`, `/etc/compaq/gotek-key` | "Transfer files", choice 3 (shown once the Pi has reached the Zero): picks the disk in the GoTEK, makes a disk from a folder, or copies one back, by asking the Pi Zero over SSH (`zero/README.md`). The key (made by `install.sh`, readable only by `desk`) can run only the Zero's floppy program |
| `/opt/compaq/lib/dustrun.py` | The DUSTRUN game |
| `/opt/compaq/lib/board.py` | The office message board (`compaq-files/.message-board.txt`, hidden so a file sent from the Compaq can't replace it) |
| `compaq-pal.service` | PAL 286 (`/opt/compaq/pal`), as its own `pal` account: camera, microphone, speaker, Claude |
| `compaq-speaker.service` | `lib/keep-speaker-on`: keeps PAL's speaker from switching itself off (a tone too low to hear on the aux socket, or reconnecting a Bluetooth one) |
| `/opt/compaq/pal/` | PAL: `pal.py` (the main loop), `senses.py` (camera, Whisper, voice), `brain.py` (Claude, personality, memory), `people.py` (known faces), `music.py` (chiptunes and singing), `jukebox.py` and `boards.py` (music and quiz pictures), `vision.py` (text art), `sfx.py` (beeps, floppy, modem), `lines.py` (offline lines), `client.py` (the menu's side) |
| `/opt/compaq/lib/pal_screen.py` | PAL's eye and typed conversation on the Compaq, drawn by the serial bridge |
| `/opt/compaq/lib/voice-open`, `voice-type`, `screen-watch` | PAL's only sudo rule (`021_compaq-pal`, as `desk`): open a listed program, type a spoken move into a text adventure, and watch the shared screen while the lobby keyboard is in use |
| `/etc/compaq/claude.env`, `pal.conf`, `pal-office.txt` | PAL's Claude key (readable only by PAL), settings, and notes about the office |
| `/var/lib/compaq-pal/` | PAL's memory: known faces (as numbers) and notes. In the encrypted backups (backup.sh) |
| `/var/lib/compaq/pal-models/`, `/opt/compaq-pal/bin/` | Face and speech models, and whisper-server (from `fetch-pal.sh`) |
| `/opt/compaq/lib/plain.py` | Filters text to plain ASCII (used by the dictionary and the welcome fortune) |
| `/opt/compaq/data/` | Lists behind the BBS, news, adventure and games menus, the feed list and newsboat settings, the repair queue's taskrc, and the web start page |
| `/run/compaq-web/viewers` | How many browsers are watching (written by the web server, shown in the menu header) |
| `/run/compaq-serial/picture.png`, `.json` | The picture the Compaq is showing, if any, for browsers (written by the bridge; a moving picture's, twice a second) |
| `/run/compaq-serial/speed`, `pilink` | The cable's everyday speed, and what PILINK managed on this Compaq (its speed and dots, or why not), for `check.sh` and PotatoTube |
| `/etc/apt/apt.conf.d/52compaq-unattended-upgrades` | Automatic updates from the Raspbian and Raspberry Pi Foundation sources (no automatic reboots) |
| `/var/lib/compaq/games/` | Text adventure story files (from `fetch-games.sh`) |
| `/etc/compaq/fixbot.env` | The FixBot API key (from `set-fixbot-key.sh`), readable only by PAL's service; kept across deploys |
| `/etc/compaq/ifixit-session.env` | The iFixit login FixBot's page uses (from `set-ifixit-login.sh`), readable only by PAL's service; kept across deploys |
| `/etc/compaq/web.env` | The office password's PBKDF2 hash (from `set-office-password.sh`). The shared session can read it (so someone at the Linux command line could try guessing the password offline: pick a long one) |
| `/etc/compaq/web-cookie.key` | Signs web sign-in cookies (root only; systemd hands it to the web server, which keeps itself off-limits to the shared account). Made by `install.sh` |
| `/etc/ssh/sshd_config.d/01-compaq-keys-only.conf` | SSH with a key only, no passwords (installed once the admin account has a key) |
| `/etc/NetworkManager/conf.d/compaq-ethernet-steady.conf` | A wired port with no DHCP server gets a 169.254 address after 15 s instead of resetting (install.sh also sets each wired profile) |
| `/etc/systemd/journald.conf.d/90-compaq.conf` | Keeps up to 32 MB of logs across restarts |
| `/etc/compaq/off` | Optional: services to keep switched off (one name a line) |
| `/home/desk/compaq-files/` | Files for Kermit transfers: documents, spreadsheets, saves, chat transcripts |
| `/etc/NetworkManager/conf.d/compaq-wifi-powersave-off.conf` | Keeps Wi-Fi power saving off |

`install.sh` also installs every package the menus need, so a fresh SD card
with Raspberry Pi OS Lite (user `compaq`, SSH on) is one `./deploy.sh`,
`fetch-games.sh` and `set-office-password.sh` away from this setup.
Raspberry Pi OS already arms the hardware watchdog (a 1 minute timeout), so a
frozen Pi reboots itself.

## Moving to a new SD card

Everything that matters is either in this folder or in the encrypted
backups (`./backup.sh`; run it first). On the new card:

1. Raspberry Pi Imager: Raspberry Pi OS Lite (32-bit), and in its settings
   hostname `compaq`, user `compaq`, SSH on with the public key
   `~/.ssh/id_ed25519_pi.pub`, and the office Wi-Fi.
2. Boot it, then on the Mac: `ssh-keygen -R pizero` (a new card has a new
   SSH identity, and ssh would rightly refuse it otherwise).
3. `./deploy.sh` (installs everything; about 10 minutes the first time).
4. `./restore.sh backups/<newest>`, with the backup password: settings and
   keys, PAL's memory, the shared files, Wi-Fi networks, the Whisper build
   and the Pi's old SSH identity come back. Then `ssh-keygen -R pizero`
   once more (the identity changed back).
5. `./deploy.sh` again, to settle permissions.
6. `./fetch-pal.sh` (PAL's models; the Whisper build came back with the
   backup), `./fetch-net.sh` (PotatoTube and Doom) and
   `ssh pizero 'sudo bash -s' < fetch-games.sh`.
7. `./check.sh`: everything should read OK.

**Or clone the running card** (how the 128 GB card was made on 2026-10-15,
in about six minutes): put the new card in a USB card reader plugged into
the Pi, check it's the reader (`lsblk`: `sda`, model `USB3.0 CRW`) and that
nothing on it is wanted, then on the Pi:

    curl -fsSL https://raw.githubusercontent.com/geerlingguy/rpi-clone/e640eff1caa29e70bb3beaea21afb36ad6311313/rpi-clone -o /tmp/rpi-clone
    sha256sum /tmp/rpi-clone        # 5594dca9129c95154c1f2e28c496feb7f4e49e5a5c356534b1341871970e74ca
    sudo systemctl stop compaq-pal
    sudo bash /tmp/rpi-clone sda -f -U
    sudo mount /dev/sda2 /mnt && sudo install -d -m 755 /mnt/boot/firmware && sudo umount /mnt
    sudo systemctl start compaq-pal

It copies the running system file by file (PAL paused so its memory
doesn't change mid-copy), fills the new card, and gives the copy its own
disk ID, editing the copy's `cmdline.txt` and `fstab` to match. The fourth
line puts back the copy's empty `/boot/firmware` folder: rpi-clone 2.0.27
deletes it while tidying up, and without it the copy can't mount its boot
partition. Then shut down, put the new card in the Pi's slot and start it:
nothing else changes (same SSH identity, settings and memory).

SSH takes keys only (no passwords) once the admin account has one, so keep
`~/.ssh/id_ed25519_pi` safe; if it's ever lost, a keyboard on the Pi's own
console (Ctrl+Alt+F1 with the TV attached) still takes the password.

## FixBot

`chat.py --backend fixbot` asks which device needs help (default: Compaq
Portable III) and passes each message to PAL's service, which holds the key
and sends it to `POST /api/plan/repair` (so the shared session, and anyone
with the office password, never sees the key). The returned `chatid` comes
back so follow-ups refine the same plan. Plans take a minute
or two. Keys are created by a FixBot workspace admin at
https://app.fixbot.pro/workspace/settings/api-keys and need an active
subscription. API reference: https://app.fixbot.pro/api-docs.

### "Hey FixBot": FixBot's own page, by voice

Say "Hey FixBot" in the lobby (or ask "Hey PAL" anything about a repair, and
PAL hands over) and FixBot takes the conversation. FixBot does all the
thinking; PAL is only its ears and voice, and Claude plays no part in it.

**With the iFixit login (`set-ifixit-login.sh`): FixBot's real page.** The
Pi's browser runs fixbot.ifixit.com logged in, exactly as on a laptop
(`lib/fixbot_page.py`), and the page itself is on the Compaq's screen in
amber dots, at its own size with its text in the Compaq's own font (VileR's
Compaq Portable III, 8x16 dots), the answers' lines a little closer, the
source numbers left out and the message box one line tall, so a 400-dot
screen holds five lines or so of an answer. FixBot's guide panel is its own
frame, drawn as iFixit draws it:

- **What they say is typed into FixBot's message box** and sent, word for
  word. Its answer is read out in PAL's voice once it's finished (its
  words, without the source numbers or the cards' small print: a guide
  card is read as "Repair guide: iPhone 12 Battery Replacement"). Answers
  took 12 to 40 seconds in tests.
- **Everything is FixBot's**: walking through a repair, "what's the next
  step?", "I'm stuck", parts, the device (FixBot picks it from what they
  say). A few words press the page's own buttons instead: "open the
  guide" (FixBot's step-by-step guide panel, which fills the screen),
  "close the guide", "take a
  picture" (a countdown, then the webcam's picture goes into FixBot's own
  photo button, and goes with the next question: FixBot named a SIM tray
  from one), "start over" and "we're done" (a fresh chat for the next
  person; also "I'm good", "close FixBot", "no thanks").
- **Leaving.** F10 at the keyboard takes the page down and ends FixBot's
  turn; so does "main menu" said anywhere in a sentence ("no thanks, take me
  back to the menu"), which opens the main menu too. PAL's name anywhere
  ("no PAL, I'm good") hands the whole sentence to PAL instead of FixBot.
  "Hey PAL, open FixBot" goes straight to FixBot listening (not the typed
  menu version).
- **Keys at the Compaq type into the page** too, as on any computer.
- **From the menu, without a word:** "Ask FixBot" (1 on the main menu)
  puts the same page on the screen and passes on what's typed at the
  keyboard (the TV's or the Compaq's), as on a laptop: Enter sends, F2
  opens the latest guide FixBot offered (and closes it again), Page Up and
  Page Down scroll whatever is on the screen, the conversation or the guide
  (a mouse wheel turned over the middle of it), Tab reaches the page's
  buttons, F10 leaves (`lib/fixbot_menu.py`; the page and login stay PAL's,
  the menu only passes keys on). The empty message box says so. Without the login, or on a screen
  that can't show the dots, it's the repair plans in text (`chat.py`).
- **On the screen:** as PAL reads an answer, the page scrolls to its start
  and follows along. Pictures in the page (a photo sent, a guide's
  thumbnail) are dithered like photos, bright parts glowing; its text stays
  crisp.
- **The login stays PAL's.** It's the `session` cookie of an iFixit
  account, in `/etc/compaq/ifixit-session.env`, readable by root and PAL
  only: not the shared session, nor anyone with the office password. The
  browser runs as PAL, is driven over its DevTools pipe (no network port),
  and starts from a fresh private profile each time. The page stays open
  between conversations and closes after 30 quiet minutes. The lobby
  page hides the account's FixBot history (the sidebar and its toggle),
  the share button and an employee account's staff tools (Admin, the
  persona switch); hidden, they can't be reached with Tab either. A
  separate lobby account would keep them off the Pi altogether.
- **It ends** when they go quiet for 20 seconds after an answer; "Hey
  FixBot" picks the same chat back up.

**With only the FixBot API key (`set-fixbot-key.sh`): repair plans.** The
Partner API (`POST /api/plan/repair`) answers with whole written repair
plans, about a minute each, text only. PAL reads them out a chunk at a
time ("next" for more) and walks through the guide FixBot recommends by
voice ("next", "back", "step 12", "photo"). It's what PAL uses when there's
no iFixit login.

**Say it in one breath with the question:** "Hey FixBot, I'm fixing my
iPhone 12 screen". Recordings of the Mac's voices, heard the way PAL hears
them, came out as "Hey Fixbot, ..." for 7 voices of 8 that way, but "Hey
FixBot" said on its own is a short clip that Whisper's small model often
garbles ("A fixed spot", "HAVicsbot"); `fixbot_mode` takes the variants it
has seen, and anything that short with a fix-word in it. A person's voice
still needs trying.

Tests: `tools/tests/fixbot_mode_test.py` (the wake words and commands,
anywhere), `fixbot_page_test.py` (FixBot's real page on the simulated PAL,
with the real login: `REAL_FIXBOT_PAGE=1`), `fixbot_menu_test.py` (the
same from the menu, typed), `fixbot_sim_test.py` and
`fixbot_real_test.py` (the plans, against a stand-in FixBot and the real
one).

## The Compaq's disks

Each image has a README.TXT. File names are DOS 8.3 with no long-name
entries, and text files use CRLF. They're all 1.2 MB 5.25" images, the
Compaq's own drive type: MS-DOS 3.1 and the Portable III's BIOS predate
1.44 MB floppies, so the GoTEK needs FlashFloppy firmware (its factory
firmware only does 720 KB and 1.44 MB). Downloads are checked against
pinned SHA-256 sums in `fetch-dos.sh`.

- `kermit`: the link to the Pi. `PI` connects with PILINK as the whole
  terminal (above). `KERMIT` is MS-DOS Kermit 3.16 set up for the Pi:
  COM1, the cable's speed (9600 baud to start with), no flow control, VT102
  (insert/delete line saves bytes), Backspace sends DEL, no status line,
  and it connects as soon as it starts, running `PILINK.COM` for pictures
  when the Pi asks. Start here.
- `boot-freedos-pi`: starts the Compaq with no DOS of its own and goes
  straight to `PI`: FreeDOS 1.3's own boot floppy (its boot sector and
  kernel, from `fetch-dos.sh`) with the Kermit disk's files and an
  `AUTOEXEC.BAT` that runs `PI`. For when the hard disk doesn't start.
  Tested by booting it in DOSBox (`tools/rig/terminal_test.py IMAGE`). Its
  `FREEDOS` folder has FDISK, FORMAT and SYS, for setting up a blank hard
  disk or CompactFlash card.
- `compaq-setup`: Compaq's own User Diagnostics 5.08 with SETUP 5.05, which
  sets the Compaq's stored settings (the hard disk's type among them). From
  PCjs's copy of the diskette, rebuilt as a 1.2 MB disk that starts by
  itself. Booted in DOSBox.
- `games-zork-zzt-digger`: Zork I-III with DOS Frotz, ZZT, Digger Remastered.
- `games-kroz`: all twelve Kroz games plus hints.
- `games-supernova-titanic`: Supernova and Beyond the Titanic.
- `office-aseasy-gwbasic`: As-Easy-As 5.7 (serial 570-110-0424-3, TRIUS's free license), GW-BASIC and VisiCalc.
- `turbo-pascal55-disk1` and `2`, `turbo-c201-disk1` to `3`: Borland's original disk sets; `A:INSTALL` from disk 1.
- `doom8088-disk1` and `2`: Doom8088, real Doom on a 286 (needs the hard disk: `A:INSTALL`).
- `word55-disk1` to `4`: Microsoft Word 5.5. `A:COPYDISK` on each, then `SETUP` from `C:\WORDSRC`; `A:WORDDEL` (disk 4) removes `C:\WORDSRC` afterwards.

Only software its owners made free is included. VisiCalc and the Borland
compilers are free for personal use only: don't share copies of those disks.

**Swapping disks without a USB stick:** with a Pi Zero W plugged into the
GoTEK in place of the stick, the menu (or PAL) picks the disk in the
drive (`zero/README.md`). Set up and tested with the Pi standing in for the
GoTEK; not yet tried with the GoTEK.

## Testing without the Compaq

`tools/screentest.py` (copy it to the Pi; needs `python3-pyte`) runs any
program on a simulated 80x24 VT100, types keys into it, and reports the screen,
the time to send it at 9600 baud, and any characters the Compaq can't show:

    python3 screentest.py --wait 3 --keys "4\r" -- /opt/compaq/menu

Two more test kits:
- **`tools/rig/`, the virtual Compaq.** The real MS-DOS Kermit and the real
  PILINK in DOSBox on the Pi, with a private bridge and session, for screen
  and picture work: `pilink_rig.py` (PILINK alone: every speed, dot for
  dot), `link_test.py` (pictures end to end, and both fallbacks) and
  `gfx_test.py` (any menu program, typed at the "Compaq").
- **`tools/tests/`.** The PAL simulator (PAL's camera, microphone and
  speaker become folders), **the whole lobby in a box** (`lobby_sim.sh`:
  the menu, the bridge, a pretend Compaq running PI and PAL, in real time,
  silent, with nothing shared touched), and tests for PAL, the web page,
  music, the PILINK encoder (`pilink_test.py`) and the TV stand-in
  (`tv_link_test.py`).

Each folder has a README.

## Adding a menu item

Drop an executable script in `pi/opt/compaq/apps/` (or a section folder),
with a `# title:` line near the top, then deploy. `lib/common.sh` has `intro`
(key tips, then Enter to start), `pause` and `choose` (a numbered list).

## When the hardware arrives

Nothing here has run on the real Compaq yet: everything was built against
the virtual one. Expect a surprise or two, and go in this order. The parts
(floppy cable, power adapters, USB A-to-A cable, bay bracket, CompactFlash
adapter and card, and a speaker bar for PAL) arrive on 20 October 2026;
`docs/shopping-list.md` lists them.

What's known about the inside (seen 2026-10-15): the floppy drive plugged
straight onto a 34-pin male header on the board behind the bay, with no
ribbon, and took the large 4-pin power plug. The hard disk (a 20 MB "Type
2") has its own 40-pin cable. The clock battery is flat: the Compaq stops
at start-up with "162 System Options Not Set" and forgets its settings
about ten minutes after it's switched off, until Compaq's SETUP is run
again. The new battery (ordered 2026-10-15) fixes that for good.

1. **The CompactFlash card, on the Pi first** (if the card reader has a CF
   slot). It's sold as a SanDisk Ultra II by a third-party seller, so it
   may be a fake that holds less than it says. In the card reader on the
   Pi:

       ssh pizero 'lsblk -d -o NAME,TRAN,SIZE,MODEL'
       ssh pizero 'sudo f3probe --destructive --time-ops /dev/sdX'

   `sdX` is the about-4 GB line in the first list: never the Pi's own
   `mmcblk0`, and not the Zero (64 MB, "File-Stor Gadget") if it's still
   plugged in. It erases the card, which is new anyway. If f3probe calls it
   fake or damaged, send it back. A card that's only slow is fine: the
   Compaq uses its first 20 MB.
2. **Flash the GoTEK** (done 2026-10-30: FlashFloppy 3.44 on an AT32F415,
   board SFRKC30.AT3, read back byte for byte). For another one: on the
   table, with **nothing else connected** (its power plug on as well
   backfed the Pi's USB port: "over-current" in `dmesg` and a GoTEK that
   answers as "UNKNOWN"). Read the big chip: AT32F435, or AT32F415 (an
   STM32F105 takes the AT32F415's file, but bridges Boot-3V and Tx-5V
   instead). Bridge J3's two holes (the square one and its neighbour, in
   the grid under the "+5V GND" power pins; FlashFloppy's photo calls them
   "the two leftmost") with a paperclip, then join the GoTEK's USB socket
   to the Pi with the A-to-A cable. `lsusb` shows `2e3c:df11 Artery-Tech
   DFU`. FlashFloppy's file is labelled for ST's ID (0483), which
   dfu-util refuses on an Artery (2e3c), so a copy is relabelled, keeping
   its DfuSe version:

       ssh pizero
       cd ~/build/flashfloppy/flashfloppy-3.44
       cp dfu/flashfloppy-at415-st105-3.44.dfu /tmp/ff.dfu
       dfu-suffix -D /tmp/ff.dfu
       dfu-suffix -v 0x2e3c -p 0xdf11 -d 0x0000 -S 0x011a -a /tmp/ff.dfu
       sudo dfu-util -d 2e3c:df11 -a 0 -s 0x08000000:unprotect:force -D /tmp/ff.dfu
       sudo dfu-util -d 2e3c:df11 -a 0 -D /tmp/ff.dfu

   (For an AT32F435, `dfu/flashfloppy-at435-3.44.dfu`.) The unprotect
   line ends in "Wrong state after command READ_UNPROTECT", which is
   expected; if the last line then says "ERASE_PAGE not correctly
   executed", run the unprotect line again, then the last one. If the
   GoTEK stops answering properly (its name reads "UNKNOWN"), unplug its
   cable for five seconds. Then take the paperclip out.
3. **Fit the GoTEK**, with the Compaq switched off and its mains lead out.
   - **The floppy cable** (CablesOnline FF-001): its lone plug at one end
     on the board's 34-pin header, and a two-row drive plug on the GoTEK.
     The red stripe is pin 1: match it to the "1" or square pad on the
     board, and to pin 1 marked on the GoTEK. On the far plug, past the
     twist, set the GoTEK's jumper to **S1**; on a plug before the twist,
     **S0**. If the Compaq doesn't find it as drive A:, try the other one.
     A plug on backwards usually just keeps the GoTEK's light on: switch
     off and turn it round.
   - **Power:** the Compaq's large plug into one of the adapters, its small
     plug into the GoTEK. Red is 5 V and yellow is 12 V; the GoTEK only
     uses 5 V. The small plug goes in one way without force; pushed in
     upside down or one pin off, it puts 12 V on the GoTEK and kills it.
   - **The Zero:** take it off the Pi and plug its data cable (in the
     Zero's inner socket, marked USB) into the GoTEK's USB socket. Leave its
     PWR socket empty: the GoTEK powers it.
   - **The bracket** can wait until it all works: the GoTEK can sit loose
     in the bay for the first tries.
4. **The serial adapter and cable** (in place since 2026-10-15): the
   adapter in a USB socket on the Pi, the null modem cable from it to the
   Compaq's 9-pin plug with pins, between the monitor socket and the wide
   printer socket. While the adapter is plugged into the Pi the TV doesn't
   show the Compaq's screen, by design: unplug it to bring the TV back.
   Check the bridge: `ssh pizero 'ls -l /dev/compaq; systemctl status
   compaq-serial'`. Any USB serial chip works; if a second adapter is ever
   added, pin the udev rule to this one with `ATTRS{serial}` (from
   `udevadm info /dev/ttyUSB0`). (Jumpers inside can make the Compaq's
   port COM2; PILINK and Kermit both follow.)
5. **First start: Compaq's SETUP.** The `compaq-setup` disk is already in
   the drive: Compaq's own diagnostics diskette with SETUP 5.05, rebuilt
   for the 1.2 MB drive. It starts by itself.
   - Switch the Compaq on. The GoTEK and the Zero get power with it, and
     the Zero takes about half a minute to start, so the Compaq gets there
     first: expect "162 System Options Not Set" (press F1) and no disk to
     start from.
   - About a minute after switching on, check the Zero is up (`ssh gotek
     floppy status` says what's in the drive), then press **Ctrl+Alt+Del**.
     A restart from the keyboard keeps the power on, so the Zero stays up
     and the Compaq starts from the GoTEK.
   - In SETUP: the hard disk is **Type 2** (20 MB: 615 cylinders, 4 heads,
     17 sectors), drive A: is 1.2 MB, and set the date and time. Save,
     then Ctrl+Alt+Del. Until the new battery is in, this step comes back
     whenever the Compaq has been off for a while.
6. **Does the hard disk start?** Take the disk out (`ssh gotek floppy
   eject`) and press Ctrl+Alt+Del.
   - DOS starts from the hard disk (C:): it works. Put the Kermit disk in
     (`ssh gotek floppy insert kermit`, or "Hey PAL, put the Kermit disk
     in") and type `A:PI` (step 7). To make it the everyday start, its
     README.TXT says how to copy it to the hard disk.
   - An error in the 1700s, or "Non-System disk": it didn't. Use the
     FreeDOS disk (`ssh gotek floppy insert boot-freedos-pi`, then
     Ctrl+Alt+Del): it starts the Compaq and goes straight to `PI`. The
     CompactFlash card can take the hard disk's place later (step 13).
7. **First connection:** `A:PI` (or the FreeDOS disk, which runs it).
   PILINK says hello, the two ends try speeds, and the shared screen
   appears within a few seconds. Then run `./check.sh`: the serial lines
   should read OK, and it should say "Pictures go through PILINK at 115200
   baud, 640x400 dots, the whole terminal". If PI stays on "waiting for the
   Raspberry Pi", try the old way, `A:KERMIT`: the bridge repaints the
   Compaq's screen as soon as Kermit opens the port (the cable turns the
   Compaq's DTR into the Pi's DSR), and on the first key after 5 quiet
   minutes, so if it starts out blank, press Enter.
8. **First picture:** open a repair guide and press P on a step with a
   photo (through Kermit, the first one takes a few seconds longer while
   Kermit starts PILINK). What `./check.sh` might say about PILINK, and
   what that means:
   - **57600 or 38400 baud:** the Compaq's serial chip (believed to be a
     16450, which holds one byte at a time) couldn't keep up any faster.
     Everything works, more slowly.
   - **640x200 dots:** the BIOS turned down the plasma's 640x400 mode.
     Pictures are still fast, at half the rows.
   - **PILINK is not on the Compaq's disk, or not answering:** through
     `KERMIT`, Kermit needs DOS's `COMMAND.COM` where DOS expects it to
     start PILINK: starting from one DOS disk and swapping to the Kermit
     disk leaves DOS without it (`PI` doesn't care). Check `PILINK.COM` is
     on the disk Kermit started from. Pictures go the slow way meanwhile.
   - **Stuck in a picture?** Ctrl+Alt+Esc at the Compaq always leaves
     PILINK. Started by Kermit, it also leaves by itself after 15 seconds
     without the Pi; as `PI`, it waits for the Pi to come back.
   - **A file transfer through `PI`:** the screen shows Kermit for the
     transfer, then PILINK comes back by itself.
9. **A blank screen after 15 minutes of a film:** the Compaq's own
   screen-save timer blanks the plasma after 15 minutes without a key, and
   PILINK takes the keys before the BIOS sees them. Any key brings it back.
   If it bites, Compaq's `MODE SCREEN-SAVE` command sets the minutes (0 to
   63).
10. **Flow control:** both ends run without it, so Ctrl-S and Ctrl-Q work
    as normal keys (WordGrinder uses them). If text ever arrives garbled or
    with gaps, switch both ends to hardware flow control (your cable is a
    "full handshaking" one, so it carries RTS/CTS): `set flow-control
    rts/cts` in `MSKERMIT.INI`, and `CRTSCTS` instead of clearing it in
    `setup_line()` in `lib/serial_bridge.py`.
11. **Backspace:** `MSKERMIT.INI` makes Backspace send DEL, which Linux
    expects. If it still prints `^H`, have the bridge turn BS (0x08) into
    DEL (0x7f) on the way in; browsers already send DEL.
12. **Faster text through Kermit (optional):** with `PI`, text already goes
    as fast as the Compaq allows; through `KERMIT` it goes at Kermit's
    speed. Once everything works at 9600, put `38400` in
    `pi/opt/compaq/data/cable-speed`, run `./deploy.sh`, `./make-disks.sh`
    and `zero/setup-zero.sh` (which sends the new disks to the Zero):
    menus paint four times faster. In the virtual Compaq, Kermit kept up
    at 38400 and dropped data at 57600. If the real one garbles text at
    38400, try `19200`.
13. **CompactFlash in place of the hard disk** (if it didn't start, or to
    retire it). Never run FDISK or FORMAT on the old hard disk: it may
    still hold the Compaq's own software.
    - Switched off: unplug the hard disk's 40-pin cable from the disk and
      put the SinLoon adapter on it instead (red stripe to pin 1), with the
      card in and the adapter set to master. Power it from the second
      small plug, red to 5 V, as in step 3.
    - SETUP (step 5) with Type 2 again. If the Compaq reports a 1700s
      error with the card, try another small type in SETUP's list: one
      owner found only one type worked with their card.
    - Start the FreeDOS disk, press Ctrl+Alt+Esc to leave the Pi for the
      DOS prompt, and run `FDISK` (one primary partition, all of the
      disk, made active), Ctrl+Alt+Del, then `FORMAT C:` and `SYS C:`.
      Take the floppy out (`ssh gotek floppy eject`) and Ctrl+Alt+Del: it
      should start FreeDOS from the card.

**PAL's speaker (since 2026-11-02): the onn speaker on an aux cord** in
the Pi's headphone socket (`SPEAKER=plughw:CARD=Headphones,DEV=0` in
`/etc/compaq/pal.conf`). The speaker switches itself off after about half
an hour without sound, so `compaq-speaker.service` (`lib/keep-speaker-on`)
plays a tone on the socket the whole time, 30 Hz at -30 dB: too low and
quiet for a small speaker to make, but enough that it never thinks it's
been left. The socket mixes up to 8 sounds, so PAL talks over it, and the
steady stream also stops the socket clicking each time PAL starts and
stops. `SPEAKER_KEEP_AWAKE=no` turns it off. Keep the speaker on charge:
it no longer switches itself off. The Pi can't tell whether anything is
plugged into its socket, so if PAL goes quiet, check the cord.

Before that it was the same speaker over Bluetooth, through `bluealsa`
(`bluez-alsa-utils`): `SPEAKER=bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp`,
and the same service connects it after every restart and whenever it's
switched back on, trying every 20 seconds. Pairing another one, once, on
the Pi: `bluetoothctl`, then `agent NoInputNoOutput`, `default-agent`,
`scan on`, `pair MAC`, `trust MAC`, and put its MAC in that `SPEAKER`
line. If the speaker in `SPEAKER` can't be reached, PAL falls back to any
USB speaker, then the headphone socket. (The USB speaker bar from 20
October did the job before them.)
