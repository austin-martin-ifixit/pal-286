# The Pi Zero W as the GoTEK's USB stick

The GoTEK in the Compaq's drive bay reads floppy disk images off a USB
stick. Plug the Pi Zero W into it instead, and the Zero is the stick, with a
library of disk images behind it. The Compaq's Pi chooses which disk is in
the drive, over Wi-Fi:

- from the menu: **Transfer files with the Compaq**, then **3. The floppy
  drive** (it appears once `setup-zero.sh` has connected the two Pis). Put a disk in, take it out, make a disk from a folder of files on
  the Pi, or copy what's on the disk in the drive back to the Pi;
- by voice: "Hey PAL, put the Doom disk in" (PAL is offered this once the
  two Pis have been connected);
- with no USB stick to carry between the Mac and the Compaq.

When the disk changes, the Compaq sees it change, as with a real drive
(`DIR A:` shows the new one). Whatever the Compaq wrote to a disk (a saved
game, a document) is kept in the library.

**Status (2026-10-15):** the Zero is set up and working: on the office
Wi-Fi, all the disks in its library, and the Compaq's Pi changing the disk
in about 15 seconds. Tested with its data cable in the Pi, which then sees
exactly what the GoTEK will: a 64 MB stick that is pulled out and put back
on each change, holding the chosen disk byte for byte. `compaq-setup` is in
the drive, ready for the first start. Not yet tried with the GoTEK, whose
parts arrive on 20 October.

## What it needs

- The Pi Zero W (you have it) and a microSD card for it, 8 GB or more.
- A micro-USB to USB-A data cable (a phone cable that carries data). It
  goes from the Zero's **inner** micro-USB socket, marked USB (not PWR), to
  the GoTEK's USB socket.
- Power: the GoTEK's USB socket powers the Zero, which then takes about
  half a minute to start after the Compaq is switched on. That's fine when
  the Compaq starts from its hard disk. To start DOS from a "floppy",
  wait a minute after switching on, then press Ctrl+Alt+Del: a restart
  from the keyboard keeps the power on, so the Zero is up by then. To
  start from a "floppy" straight away, power the Zero from a charger on
  its PWR socket instead, and stop the data cable's 5 V wire reaching the
  GoTEK (a "USB power blocker" adapter, or tape over the plug's power pin):
  otherwise the Zero powers the GoTEK and the Compaq's drive electronics
  when the Compaq is off.

## Setting it up

1. **The card**, written by the Compaq's Pi: put the SD card in a USB card
   reader plugged into the Pi, then on the Mac
   `ssh pizero 'sudo bash -s' < zero/write-card.sh`. It writes the newest
   Raspberry Pi OS Lite (32-bit), checked against Raspberry Pi's checksum,
   and sets up its first start: name `gotek`, user `compaq` (SSH with the
   same keys as the Compaq's Pi), and the Pi's own Wi-Fi connection, copied
   root to root so nobody types the password (the Zero only does 2.4 GHz:
   slow, but a floppy is only 1.2 MB). It won't touch anything but a USB
   card reader holding a card under 70 GB. (Writing a card on the Mac
   itself needs a password and, for the terminal, macOS's permission to
   write raw disks: the Pi needs neither.)
2. **Tell the Mac where it is.** Add this to `~/.ssh/config`:

       Host gotek
         HostName gotek.local
         User compaq
         IdentityFile ~/.ssh/id_ed25519_pi
         IdentitiesOnly yes

3. **Boot the Zero** (any USB power for now), then on the Mac:

       ./deploy.sh            (gives the Compaq's Pi its key for the Zero)
       ./make-disks.sh        (the disk images, if disks/1200k is empty)
       zero/setup-zero.sh

   It installs the floppy program and its start-up service, makes the
   Zero's inner USB socket a device instead of a host (that needs a
   restart, which it does), lets the Compaq's Pi in with a key that can run
   only the floppy program, copies every disk image in `disks/1200k` into
   the library, and puts the Kermit disk in the drive.
4. **Plug the Zero into the GoTEK** with the data cable. FlashFloppy sees a
   USB stick holding one disk and its settings (`interface = ibmpc`).

## How it works

`floppy` (here; installed on the Zero as `/usr/local/bin/floppy`) keeps:

- the library, `/var/lib/gotek/disks/NAME.img`;
- the "stick", `/var/lib/gotek/stick.img`, a 64 MB FAT32 file holding
  `FF.CFG` and `DISK.IMG`, the disk in the drive;
- which disk that is, in `/var/lib/gotek/in-drive`.

The Zero's USB controller shows `stick.img` to the GoTEK as a USB stick
(Linux's mass-storage gadget). To change the disk, `floppy` unplugs the
stick (it disconnects from the USB socket, so to the GoTEK it's pulled
out), copies the disk the Compaq used back
into the library, puts the new one in as `DISK.IMG`, and plugs it back in.
The image is never changed while the GoTEK can see it.

The Compaq's Pi asks over SSH (`lib/floppies.py`), with a key made by
`install.sh` (`/etc/compaq/gotek-key`). On the Zero that key is limited to
`floppy` and its commands: `list`, `status`, `insert NAME`, `eject`,
`put NAME` (an image on standard input), `get NAME` and `remove NAME`.

## Testing without the Zero

On the Compaq's Pi, with the rig copied there (`tools/rig/setup.sh`):

    python3 /tmp/rig/floppy_test.py /tmp/rig/floppy
    python3 /tmp/rig/floppies_test.py /tmp/rig/lib /tmp/rig/floppy

The first runs the floppy program with its USB side switched off; the
second puts the Pi's menu code in front of it, with a stand-in for SSH.

## Not known until it's tried

- That FlashFloppy notices the stick being pulled out and put back as
  quickly as a real one. Other owners do the same with a Zero (FlashFloppy
  discussion 451; ADF On-The-Go for the Amiga), by unplugging the gadget
  between images, as this does.
- Whether the GoTEK's USB socket gives the Zero enough power with its
  Wi-Fi on. If the Zero keeps restarting, power it separately (above).
