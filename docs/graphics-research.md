# Graphics on the Compaq: the plan, and what was measured

The wider question, what else could carry data to the Compaq faster and
what to buy, is answered in
`reports/Compaq Portable III faster links.md`, with its sources in
`research_notes/`. This file is the graphics side: what limits pictures,
what was built to get past it, and the numbers.

Facts are marked **measured** (on the virtual Compaq: the real MS-DOS
Kermit 3.16 and the real PILINK.COM in DOSBox at roughly a 286's speed, or
against the real encoder with a pretend cable), **sourced** (see the
report) or **estimate**. Nothing here has run on the real Compaq yet.

## The short answer

Austin's suspicion was right: the limit is the cable's path, not the Pi, the
Compaq or the screen. But it's less the wire than what sat on it.

- The 286 can fill the screen far faster than any serial cable can feed it.
  A 4.77 MHz IBM PC writes screen memory at 240 KB a second (sourced), and
  the 286 is several times quicker. A PC serial port tops out at 115200
  baud, 11.5 KB a second.
- At 9600 baud through Kermit the cable carried 1 KB a second, and Kermit's
  own drawing code set the pace: it garbles sixel pictures at 57600 baud
  (measured).
- A terminal never says when a key is let go, which is why Doom in text
  could only be tapped at.

So Kermit was taken out of the picture path. PILINK.COM, a 2.6 KB DOS
program (`dos/pilink.asm`), reads the serial port itself, writes what
arrives straight into video memory, and sends each key press and release
back. The Pi keeps a copy of the screen and sends only what changed. The
cable then carries its full speed: 12 times today's.

## Measured

**Still pictures** (the whole chain: the bridge, Kermit launching PILINK,
`tools/rig/link_test.py`):

| | Through Kermit at 9600 | Through PILINK at 115200 |
|---|---|---|
| A repair photo, full screen | 9.6 s | 0.9 s |
| A QR code | 1.7 s | 0.7 s |
| From asking to the picture starting, the first time | at once | about 2 s (Kermit starts PILINK; the ends agree a speed) |

**PILINK alone, a full 640x200 screen of random dots** (the worst case:
16,014 bytes, nothing to leave out; every dot checked against a
screenshot; `tools/rig/pilink_rig.py`):

| Cable speed | Time | Rate | Dots wrong |
|---|---|---|---|
| 38400 | 3.87 s | 4.1 KB/s | 0 |
| 57600 | 2.61 s | 6.1 KB/s | 0 |
| 115200 | 1.34 s | 11.9 KB/s | 0 |

The same with the serial chip's buffer switched off (the Compaq's chip is
believed to be a 16450, which has none; sourced from a community
schematic) and with DOSBox dropping any byte the program was late for.

**Kermit's own sixel drawing at higher speeds** (one 9.2 KB photo, no flow
control; `tools/rig/speed_test.py`): 10.9 s at 9600, 5.6 s at 19200, 2.7 s
at 38400, garbled at 57600. So 38400 is the most Kermit takes, and is
worth having for text.

**Moving pictures at 115200** (11,520 bytes a second), with ordered
dithering, so what stays still stays the same dots:

| What | Picture | Bytes a frame | Frames a second |
|---|---|---|---|
| Film, a calm scene | 320x200 | about 1,000 | 9.3 |
| Film, a busy scene | 320x200 | about 1,700 | 6.0 |
| Film, a busy scene | 320x100 | about 540 | 12.9 |
| Film, a busy scene | 160x100 | about 430 | 13.9 |
| The same film through the real PILINK, start to end | 320x200 | | 6.5 |
| Doom, its demo and a walk | 320x200 | about 2,100 to 2,600 | 3.2 to 4.0 |
| Doom, its demo and a walk | 320x100 | about 1,100 to 1,700 | 4.7 to 7.2 |
| A bouncing ball (little changes) | 320x200 | | 10 through the real PILINK |

(`tools/tests/video_rate.py` and `doom_rate.py`: the real encoder, the
cable pretended. The film is Big Buck Bunny, asked for at 15 frames a
second.) At 38400 baud the busy scene gets 1.3 frames a second at 320x200
and 6.5 at 320x100.

Error-diffusion dithering, which looks finer on a still photo, makes
almost every dot differ from frame to frame: the same busy scene needs
4,500 bytes a frame and gets 2.5 frames a second. Hence ordered dithering
for anything that moves, and error diffusion for stills.

## How it works, in a paragraph

The bridge sends Kermit `ESC _ run pilink /k ESC \\` (Kermit runs commands
the host sends when `SET TERMINAL APC UNCHECKED` is set; measured: with
`ON` it refuses RUN). PILINK says hello; the Pi proposes 115200, sends a
2 KB test pattern, and both fall back to 57600, then 38400, then Kermit's
own speed, until one passes. The Pi asks the BIOS for the plasma's 640x400
mode (mode 40h) and uses the CGA's 640x200 if it's refused. Then screens
go as "skip this many bytes, put these here, repeat this byte": only what
changed since the last one. PILINK answers when each screen has arrived,
so the Pi always sends the newest picture and never queues stale ones. If
bytes are lost PILINK says so, waits for a quiet line, and the Pi sends
the whole screen again. A quit command (or 15 seconds of silence, or
Ctrl+Alt+Esc) hands the Compaq back to Kermit. The details are at the top
of `dos/pilink.asm`; the Pi's side is `lib/pilink.py`.

## The machine (sourced; see the report)

**Video**
- A CGA-compatible display on the plasma: 640x200, 320x200 (the four
  "colours" show as dot patterns) and 640x400.
- The 640x400 mode is BIOS mode 40h, the same number and memory layout as
  the AT&T 6300 and Olivetti M24: 32 KB at segment B800, the rows dealt in
  turn to four 8 KB banks. Three code bases agree on the layout (86Box,
  MicroWeb, MAME). On the Compaq the switch is port 23C6h bit 0.
- One colour in graphics: on or off.
- The Compaq's own screen-save timer blanks the panel after 15 minutes
  without a key (port 27C6h holds the minutes).

**Serial:** one 9-pin port, a 16450 chip by a community schematic (one byte
held at a time, so a late read loses a byte). 115200 baud is the ceiling
of any PC serial port. Jumpers can make it COM1 or COM2.

**Parallel:** a printer port, output-only by the same schematic. A link
through it would read four bits at a time on the status lines.

**Expansion:** no slots inside. A 96-pin connector on the back carries
nearly the whole AT bus, for Compaq's rare two-slot expansion unit.

## What's built on it

- **Photos** in guides, web search and the photo booth: a second or two,
  and in 640x400 where the BIOS allows.
- **PotatoTube HD:** H and a number at PotatoTube's list. The text-art
  PotatoTube stays, and stays the default.
- **Doom in real dots**, with keys that can be held.
- **The TV stand-in** plays PILINK too, at a 115200 cable's pace.
- **PILINK as the whole terminal** (`PI`), and **PAL's eye in real dots**
  when it runs.

Kept as they are, on purpose: text-art PotatoTube, DUSTRUN, the text
adventures, PAL's text scenes.

## What could come next

1. **The real Compaq.** Follow the README's checklist. The first picture
   answers the open questions: the speed its serial chip manages, and
   whether its BIOS takes mode 40h.
2. **38400 for text through Kermit**, once it has connected at 9600: one
   setting (`pi/opt/compaq/data/cable-speed`). With `PI` it doesn't matter.
3. **PILINK as the whole terminal: built (2026-10-14).** `PI` on the Kermit
   disk runs PILINK alone; the Pi sends the text too, into the Compaq's
   own text mode (a full screen is about 1.8 KB, a scrolled line about 80
   bytes; through Kermit a screen is about 2 KB at 9600). Pictures need no
   handover. Tested in the rig; see the README.
4. **PAL in graphics: built.** With `PI` running, PAL's eye, the quiz
   board, the jukebox (a real piano keyboard) and the mirror (the camera
   dithered) are drawn in real dots, and its "got it" tick and power-on beep
   come from the Compaq's own speaker. The lobby TV plays a Compaq running
   PI, so all of it shows there now.
5. **Native programs, once there's a disk to boot from:** Wolfenstein 3D
   for CGA, Doom8088 (the floppies are built), and MicroWeb over a serial
   network link.
6. **A faster link than serial** (the report compares them): a pocket
   Ethernet adapter on the printer port, or a parallel-port board on the
   Pi with a PILINK that reads the printer port. The picture commands are
   the same whatever carries them.

Not recommended: driving the plasma panel directly from the Pi. Its
interface is undocumented, it runs on about 200 V, and one mistake ends an
irreplaceable panel.
