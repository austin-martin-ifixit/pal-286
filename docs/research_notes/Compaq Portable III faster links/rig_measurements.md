# Measurements on the virtual Compaq (2026-10-13)

These are measured, not researched. The test rig is the real MS-DOS Kermit
3.16 and our own DOS program running in DOSBox 0.74 on the Raspberry Pi
(machine=cga, cycles=fixed 3000, roughly a 12 MHz 286), with COM1 as a null
modem to a TCP socket. Nothing here has run on the real Compaq yet: DOSBox's
timing is not a real 286's and its serial chip is more forgiving, so treat
the top speeds as a best case until the real machine confirms them.

## Takeaway

Taking Kermit out of the picture path works, and the cable then carries its
full rated speed. A custom DOS program (PILINK.COM, 2.6 KB, in
`compaq-pi/dos/pilink.asm`) reads the serial port itself, writes straight
into video memory and reports key presses and releases. In the rig it runs
at 115200 baud with no errors, 12 times today's 9600 baud.

## Findings (all measured in the rig)

- **Kermit can be told to launch a DOS program.** With `SET TERMINAL APC
  UNCHECKED` in MSKERMIT.INI, the Pi sending `ESC _ run hello ESC \` made
  Kermit run the program and return to the terminal screen by itself. With
  `SET TERMINAL APC ON` the same command was refused (`tools/rig/apc_test.py`).
- **Kermit's own sixel pictures (earlier measurement, same rig):** a 9.2 KB
  photo took 10.9 s at 9600 baud, 5.6 s at 19200, 2.7 s at 38400, and was
  garbled at 57600.
- **PILINK, a full 640x200 screen of random dots (the worst case, 16,014
  bytes, nothing compresses), every dot checked against a screenshot:**

  | Cable speed | Time for the full screen | Rate | Dots wrong |
  |---|---|---|---|
  | 38400 | 3.87 s | 4.1 KB/s | 0 |
  | 57600 | 2.61 s | 6.1 KB/s | 0 |
  | 115200 | 1.34 s | 11.9 KB/s | 0 |

  The same held with the serial chip's 16-byte buffer (FIFO) switched off,
  which is how the Compaq's 16450 chip behaves, and with DOSBox told to
  drop any byte the program was late for (`rxdelay:0`).
- **A typical picture is much smaller than the worst case.** A test picture
  of shapes and patterns was 4,745 bytes and painted in 0.40 s at 115200.
- **Smaller pictures, fatter dots (PILINK widens them on the Compaq, so
  fewer bytes cross the cable). Worst-case noise at 115200:**

  | Picture | Bytes for a full screen | Time |
  |---|---|---|
  | 640x200 | 16,014 | 1.34 s |
  | 320x200 (dots 2 wide) | 8,013 | 0.66 s |
  | 320x100 (dots 2 wide, 2 tall) | 4,008 | 0.33 s |
  | 160x100 (dots 4 wide, 2 tall) | 2,008 | 0.16 s |

- **Key presses and releases both arrive.** Pressing and releasing A gave
  scancode 1Eh (down) then 9Eh (up). A terminal can only report the press.
- **Lost bytes are recovered.** A command cut off halfway made PILINK report
  the loss, wait for a quiet line, and accept a fresh full screen with no
  dots wrong.
- **Speed changes are negotiated.** The Pi asks for a new speed, sends a
  2 KB test pattern, and both ends fall back if it does not arrive intact.

## What this does not show

- The real Compaq's serial chip is believed to be a 16450 with no buffer.
  Whether a real 12 MHz 286 keeps up at 115200 or only 57600 or 38400 is
  unknown until tested. The program picks the fastest speed that passes its
  own test, so a slower machine still works, more slowly.
- The 640x400 mode (BIOS mode 40h) cannot be tested in DOSBox, which has no
  such mode. The layout PILINK uses comes from three code bases that agree
  (86Box, MicroWeb, MAME).
- Frame rates for moving pictures were measured afterwards and are in
  `docs/graphics-research.md`: a test film at 320x200 got 9.3 frames a
  second in a calm scene and 6.0 in a busy one against a pretend 115200
  cable, and 6.5 through the real PILINK from start to end; Doom got 3 to 4
  at 320x200 and 5 to 7 at 320x100.
