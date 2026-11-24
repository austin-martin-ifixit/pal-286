# Storage paths for the Compaq Portable III: floppy (GoTEK), IDE hard disk, and Pi-served storage

Researched 2026-10-13. Every line under "Cited Findings" carries its source. Lines under "Inferences" are my own reasoning or estimates and are labelled as such. "Snippet only" means I saw the claim in a search-result extract and could not open the page itself (Vogons refused connections during this session).

The single most useful primary source found: Compaq's own Service Quick Reference Guide pages for the Portable III (scanned, with an OCR text layer), hosted at minuszerodegrees.net. The OCR is garbled in places; where I reconstructed a table row from jumbled OCR order I say so.

Corrections to `docs/graphics-research.md`:
- "Which ROM revision supports 1.44 MB is unknown" is now answered: **system ROM N.2 or later**, and Compaq also required MS-DOS 3.31 (see question 2).
- "Native DOS programs need a hard disk, or a GoTEK with 1.44 MB support" should read "a GoTEK with **1.2 MB** images": that is the combination with a positive report on a 286 AT, and it needs no ROM or DOS change.
- "mTCP telnet with sixel since October 2026" and "NetDrive mounts a disk image served by the Pi" are confirmed (mTCP release 2026-10-10).
- "SLIP at about 5-7 KB/s" was not confirmed by any measurement I could find; treat it as an estimate.

## 1. GoTEK SFR1M44-U100 with FlashFloppy in a Portable III (settings, jumpers, cable, chips, flashing, mounting)

### Takeaway
Use `interface = ibmpc`, jumper S1 only, on the twisted end of the cable, keep the Compaq's drive type at 1.2 MB, and use 1,228,800-byte images; FlashFloppy recognises that size on its own and needs no RPM setting. Avoid 360 KB images (unreliable on a 1.2 MB-configured AT) and avoid `ibmpc-hdout`. New GoTEKs almost always have an Artery chip, flashed over a USB A-to-A cable.

### Cited Findings

FF.CFG and jumpers
- For IBM PC hosts the FlashFloppy wiki says IBM-PC interface mode must be configured, either by a strap on jumper JC or by `interface = ibmpc` in FF.CFG; put the select jumper on **S1 only** and leave S0, S2 and MO open. — [FlashFloppy wiki: Host Platforms](https://github.com/keirf/flashfloppy/wiki/Host-Platforms)
- A twisted cable is "normally not used" with FlashFloppy except when the GoTEK is drive A on an IBM PC compatible, which is the case the twist was designed for. — [FlashFloppy wiki: Host Platforms](https://github.com/keirf/flashfloppy/wiki/Host-Platforms)
- The example FF.CFG defines the interface modes as: `ibmpc: P2=unused, P34=DSKCHG (IBM PC interface)` and `ibmpc-hdout: P2=HD_OUT, P34=DSKCHG (not generally needed: prefer ibmpc)`. The default is `interface = jc` (JC open = shugart, closed = ibmpc). — [FlashFloppy examples/FF.CFG](https://raw.githubusercontent.com/keirf/FlashFloppy/master/examples/FF.CFG)
- `pin02` and `pin34` accept `auto, nc, low, high, rdy, nrdy, dens, ndens, chg, nchg`; `auto` derives both from `interface=`. `nc` is described as "Unused/No Connection [eg. if pin is an input (host->drive) on your host]". — [FlashFloppy examples/FF.CFG](https://raw.githubusercontent.com/keirf/FlashFloppy/master/examples/FF.CFG)
- `host = pc-dos` means "geometry determined from Bios Parameter Block"; `host = unspecified` (the default) means "Common default geometries (including IBM PC)". — [FlashFloppy examples/FF.CFG](https://raw.githubusercontent.com/keirf/FlashFloppy/master/examples/FF.CFG)
- Other defaults that matter and can stay as they are: `write-protect = no`, `track-change = instant`, `write-drain = instant`, `index-suppression = yes`, `head-settle-ms = 12`, `motor-delay = ignore` (the motor line is not connected on a standard GoTEK), `chgrst = step` (the disk-change signal resets on a step pulse). — [FlashFloppy examples/FF.CFG](https://raw.githubusercontent.com/keirf/FlashFloppy/master/examples/FF.CFG)
- On some boards (the first SFRKC30.AT2 revision) there is no JC jumper, so PC mode can only be set in FF.CFG. — [FlashFloppy wiki: Gotek Models](https://github.com/keirf/flashfloppy/wiki/Gotek-Models)

1.2 MB images and "360 RPM"
- FlashFloppy's raw-image table has an explicit entry for the AT format: 15 sectors, 2 sides, 80 cylinders, **360 RPM**, commented `/* 1.2MB */`. With `host = unspecified`, an image is matched to this table by file size (cylinders x sectors x 512 x sides), so a 1,228,800-byte .IMG is emulated as a true 360 RPM, 500 kbit/s disk with no extra configuration. — [FlashFloppy src/image/img.c](https://github.com/keirf/FlashFloppy/blob/master/src/image/img.c)
- With `host = pc-dos`, the same file is opened from its boot-sector BPB using the default layout, whose `rpm` is 300; the data rate is then inferred from the track length (code comment: `DD=250, HD=500, ED=1000`). So under `pc-dos` a 1.2 MB image is presented at 500 kbit/s but on a 300 RPM "disk". — [FlashFloppy src/image/img.c](https://github.com/keirf/FlashFloppy/blob/master/src/image/img.c)
- IMG.CFG can override per-image geometry, including `rpm` ("Rotational RPM. Default is 300"), `rate` ("Data rate in kHz ... 0 = based on recording mode and size of track") and `step` ("Number of drive-head steps between cylinders. Default is 1"). Tags match on file name and optionally on exact file size, e.g. `[dsdd80::737280]`. — [FlashFloppy examples/IMG.CFG](https://raw.githubusercontent.com/keirf/FlashFloppy/master/examples/IMG.CFG)
- Field report, IBM 5170 (the original 286 AT): with `interface = ibmpc`, `host = pc-dos`, `pin02 = auto`, `pin34 = auto`, a 1.2 MB image (1,228,800 bytes) "works reliably" and boots; 360 KB images (368,640 bytes) do not boot or boot only occasionally, with the drive set to either 360K or 1.2MB in SETUP; `pin02 = dens` made no difference. The same 360 KB images work on an IBM 5150 with the same GoTEK. The issue is open with no maintainer reply. — [FlashFloppy issue #1072](https://github.com/keirf/flashfloppy/issues/1072)

Portable III and Portable 386 owner reports
- VCFed thread (Feb 2020), Portable III with a FlashFloppy GoTEK as the only floppy: the machine's cable **has a twist**; the owner got "162 - System Options Not Set" and no boot whatever the jumpers (S0, S1, JC tried). After contacting Retropaq he reported: "you can't boot the compaq from the gotek the first time" until the machine has been booted once from a 5.25-inch floppy carrying the setup image. The thread ends without a confirmed final configuration, FF.CFG, or ROM revision. — [VCFed: Compaq Portable III and Gotek Floppy Emulator](https://forum.vcfed.org/index.php?threads/74838/)
- Ret.rocks (restorer of about eight Portable III/386 machines): "I did have some success with Gotek although it all seemed really random as to what sized floppy images it wanted to boot from." He configured the GoTEK as a 1.44 MB drive in SETUP and it booted a 720 KB setup image, which a real 1.44 MB drive would not. His jumper positions are shown only in a photo. — [Ret.rocks: Compaq Portable III and 386 restoration notes](https://ret.rocks/index.php/one-off-works/compaq-portable-iii)
- Retropaq (Portable 386, same chassis) runs a GoTEK and fits 3.5-inch devices in the 5.25-inch bay "using a caddy"; a commenter with a "portable 3" using a GoTEK as drive B said setup only recognised it as 1.2 MB, not 1.44 MB. No FF.CFG, jumper or bracket details are given. — [Retropaq: The Floppy Drive](https://retropaq.com/the-floppy-drive/)

Which chip, and how each is flashed
- Three MCUs exist: STM32F105 (72 MHz, 64 kB SRAM; "not used in production since early 2021"), Artery AT32F415 (32 kB SRAM, shipped from spring 2021; the small RAM makes track formatting and high-density HFE writes unreliable) and Artery AT32F435 (288 MHz, 384 kB SRAM, shipped from July 2022, the only one on PCB SFRKC30.AT4.35). The wiki says new GoTEKs most likely have an Artery MCU and strongly recommends the AT32F435. — [FlashFloppy wiki: Gotek Models](https://github.com/keirf/flashfloppy/wiki/Gotek-Models)
- Identification: open the case and read the chip, or run FlashFloppy with no USB stick and read the SRAM size it reports (right button on a three-digit display). PCB SFRC922D is shared by STM32F105 and AT32F415, so the case alone does not tell. Avoid "UFA" models, 26-pin DU26/TU26 models, and CH32F103 boards. — [FlashFloppy wiki: Gotek Models](https://github.com/keirf/flashfloppy/wiki/Gotek-Models)
- Artery chips (AT32F415/AT32F435): bridge the two leftmost pads of the programming header to enter the bootloader, connect a USB A-to-A cable, and use Artery ISP Programmer (Windows) in "USB DFU" mode: clear protection (erases flash), then download `flashfloppy-at415-st105-<ver>.hex` or `flashfloppy-at435-<ver>.hex`. Linux instructions are in discussion #698. — [FlashFloppy wiki: Firmware Programming](https://github.com/keirf/flashfloppy/wiki/Firmware-Programming)
- STM32F105, USB method: temporarily jumper Boot to 3V and Tx to 5V, connect a USB A-to-A cable, then run `dfu-util -a 0 -s :unprotect:force -D flashfloppy-at415-st105-<ver>.dfu` (only needed on a read-protected, factory-fresh unit; wait a few seconds for it to re-enumerate) followed by `dfu-util -a 0 -D flashfloppy-at415-st105-<ver>.dfu`. Serial method: a USB-TTL adapter with `stm32flash -k /dev/ttyUSB0` then `stm32flash -vw flashfloppy-at415-st105-<ver>.hex /dev/ttyUSB0`. The wiki notes macOS can have DFU connection trouble and suggests an external hub. — [FlashFloppy wiki: Firmware Programming](https://github.com/keirf/flashfloppy/wiki/Firmware-Programming)
- The newest release in the FlashFloppy repository on 2026-10-13 is v3.44 (12 April 2025). The AT32F435 has cached HFE and QD image data since v3.34. — [FlashFloppy RELEASE_NOTES](https://github.com/keirf/FlashFloppy/blob/master/RELEASE_NOTES)
- The USB stick must be FAT32 (exFAT and NTFS are not supported). (Snippet only.) — [FlashFloppy wiki: Initial Setup](https://github.com/keirf/FlashFloppy/wiki/Initial-Setup)

Bay and cables
- The Portable III has two bays: one "the width of a normal 5.25-inch bay but not as high" holding a slimline high-density 5.25-inch floppy, and a full-sized bay holding the hard disk. — [John Elliott: Compaq Portable III](https://www.seasip.info/VintagePC/compaq3.html)
- Ret.rocks swapped the bays on one machine: CF adapter in the floppy bay, GoTEK in the hard-disk side, trimming 5-10 mm off a printed mount. — [Ret.rocks](https://ret.rocks/index.php/one-off-works/compaq-portable-iii)
- Compaq listed two diskette signal cables for the Portable III: 107177-001 "Single Drive" and 107177-002 "Dual Drives", plus a "Mass Storage Power" cable (107176-001 in the OCR). — [Compaq Service Quick Reference Guide, Portable III pages](https://www.minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Information%20from%20the%20CSQRG.pdf)

### Inferences
- Recommended starting FF.CFG (my synthesis of the sources above, untested on a Portable III):
  ```
  interface = ibmpc
  host = unspecified
  pin02 = nc
  pin34 = chg
  ```
  `pin02 = nc` and `pin34 = chg` are what `auto` already produces under `ibmpc`; writing them out guards against a stray JC strap. `host = unspecified` selects the built-in 360 RPM 1.2 MB entry; `host = pc-dos` also works on a 5170 per issue #1072.
- A PC floppy controller locks to the data rate, not the spindle speed, so the 300 RPM emulation under `host = pc-dos` still reads correctly (consistent with issue #1072). The practical difference is speed: 360 RPM gives six tracks a second, 300 RPM gives five. Estimate, not measured.
- Do not use `ibmpc-hdout`: on an AT 1.2 MB interface pin 2 is driven by the controller (density/write-current select), so the GoTEK should not drive it. This is general AT knowledge, not checked against a Compaq schematic; FF.CFG's own note on `nc` points the same way.
- The 360 KB failures in issue #1072 are probably a data-rate mismatch: an AT expects a double-density disk in a 1.2 MB drive at 300 kbit/s with double-stepping, while FlashFloppy presents a 360 KB image at 250 kbit/s on 40 single-stepped cylinders. An IMG.CFG tag with `cyls = 40`, `step = 2`, `secs = 9`, `bps = 512`, `rpm = 360`, `rate = 300` might fix it. Untested guess. The same mismatch would explain Ret.rocks' "random" results.
- Practical rule: make every image 1.2 MB (80 x 2 x 15 x 512 = 1,228,800 bytes), including the one that carries Compaq SETUP (see question 4).
- If the Compaq cable is twisted (the VCFed owner's was), S1 at the twisted end is drive A. If the cable turns out to be straight, S1 would answer as drive B, and the select jumper would need to move; check the cable before blaming the firmware.
- The "can't boot from the GoTEK the first time" report most likely means CMOS was invalid (dead battery), not a GoTEK fault: the machine needs a valid diskette type in CMOS first.
- The GoTEK takes the small 4-pin 3.5-inch power plug. Whether the Compaq's drive power lead ends in that or in the large 4-pin plug was not found; budget for a large-to-small power adapter and a 3.5-to-5.25-inch bay bracket.

### Gaps
- No report gives a complete, confirmed FF.CFG plus jumper set for a Portable III, Portable II or Deskpro 286. The closest positive evidence is the IBM 5170 report.
- The height of the Portable III floppy bay in millimetres, and the power connector type on its drive lead, were not found.
- The SFR1M44-U100's current chip cannot be known without opening the unit; sellers do not state it reliably.
- Whether FlashFloppy has released anything newer than v3.44 outside the master branch's RELEASE_NOTES was not checked.
- The Linux flashing steps for Artery chips (discussion #698) were not read.

## 2. Does the Portable III BIOS support 3.5-inch 720 KB or 1.44 MB drives, and a drive B? Which ROM revisions? Can the real drive and the GoTEK coexist?

### Takeaway
Compaq's service guide says the 1.44 MB drive needs **system ROM N.2 or later** and Compaq MS-DOS 3.31; ROM K (January 1987) does not qualify. A second diskette drive is supported (Compaq sold a dual-drive cable), so the 5.25-inch drive and a GoTEK can share the controller. With MS-DOS 3.1 the question is moot: stay at 1.2 MB.

### Cited Findings
- Compaq listed three diskette drives for the Portable III: 360 KB (107360-001), 1.2 MB (107359-001) and 1.44 MB (footnoted). The footnote reads, through OCR noise: requires system ROM **N.2 or later** for use with MS-DOS, and system ROM **P.2 or later** for use with MS OS/2 version 1.1; requires **MS-DOS version 3.31 revision A if installed as drive B** and **MS-DOS version 3.31 revision B if installed as drive A**. — [Compaq Service Quick Reference Guide, Portable III pages](https://www.minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Information%20from%20the%20CSQRG.pdf)
- System ROM revisions and part numbers (odd/even): K 106778-002/106779-002 (16 KB each); N.2 107824-001/107825-001 (32 KB); P.2 109737-001/109738-001 (32 KB); R.2 109737-002/109738-002 (32 KB). ROM sockets are U72 (odd) and U89 (even). — [Compaq Service Quick Reference Guide, Portable III pages](https://www.minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Information%20from%20the%20CSQRG.pdf)
- Dates: K is 01/29/1987, P.2 is 01/28/1988, R.2 is 11/14/1988; N.2's date is unknown. The chips are 27256/27C256 EPROMs, split odd and even. — [Internet Archive: Compaq Portable III BIOS Revisions](https://archive.org/details/compaq-portable-iii-bios)
- John Elliott's machine has revision K dated 29 January 1987; he notes the case "would also permit a twin-floppy configuration". — [John Elliott: Compaq Portable III](https://www.seasip.info/VintagePC/compaq3.html)
- Compaq's cable list has a diskette signal cable for "Dual Drives" (107177-002) alongside the single-drive cable, and the system board has jumpers for "Diskette drive primary address / secondary address". — [Compaq Service Quick Reference Guide, Portable III pages](https://www.minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Information%20from%20the%20CSQRG.pdf)
- Jumper E1 selects "CPU speed 12 or 8 MHz when accessing diskette drive" versus "CPU speed 8 MHz when accessing diskette drive". — [Compaq Service Quick Reference Guide, Portable III pages](https://www.minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Information%20from%20the%20CSQRG.pdf)
- A Portable III owner ran a GoTEK as drive B and found setup treated it as 1.2 MB, not 1.44 MB. — [Retropaq: The Floppy Drive (comments)](https://retropaq.com/the-floppy-drive/)
- Ret.rocks says SETUP offers "160k 5.25, 360k 5.25, 720k 3.5 and 1.44Mb 3.5" and that with a dead CMOS battery the machine "will revert to expecting either a 360k or 720k disk only". The same page says these machines "only came with 320k 5.25 ... or a 720k 3.5 floppy drive", which is wrong for the Portable III (standard drive: 1.2 MB), so treat its floppy details with caution; the page mixes Portable III and Portable 386. — [Ret.rocks](https://ret.rocks/index.php/one-off-works/compaq-portable-iii); contradicted by [Wikipedia: Compaq Portable III](https://en.wikipedia.org/wiki/Compaq_Portable_III) and the Compaq parts list above
- The Portable 386's ROM accepts 3.5-inch 1.44 MB drives, selected in the diagnostics utility. — [Retropaq: The Floppy Drive](https://retropaq.com/the-floppy-drive/)

### Inferences
- If this machine still has ROM K (likely for a 1987 Model 20; the 16 KB chips and the 01/29/87 date identify it), 1.44 MB is not supported by the ROM. Reading the BIOS date at F000:FFF5 with DEBUG is the usual way to check; that address is the PC convention, not something I confirmed for Compaq.
- Even with ROM N.2 or later, MS-DOS 3.1 has no 1.44 MB format; Compaq tied the drive to MS-DOS 3.31. So 1.44 MB only becomes useful together with a newer DOS.
- 720 KB support is not addressed by the Compaq parts list (no 720 KB drive is listed for the Portable III). The SETUP program on the later diagnostics disk may offer 720 KB regardless of what the ROM can do. Unresolved.
- Both drives at once: electrically yes (dual-drive cable, drive B supported). A standard PC floppy cable with a twist and two 34-pin IDC sockets should do it: drive after the twist is A, drive before it is B, both jumpered as the second select (S1 on the GoTEK). Making the GoTEK A: and the real drive B: keeps booting from images. There is only one floppy bay, so one of the two has to live in the hard-disk bay or outside the case. My reasoning; not from a Portable III report.

### Gaps
- Which ROM revision this particular machine has is unknown until it is read.
- The Compaq maintenance and service guide for the Portable III itself (as opposed to the quick-reference pages) was not found online; the Portable II and Portable 386 guides are on minuszerodegrees.net.
- Whether ROM K's SETUP accepts two 1.2 MB drives was not confirmed by a primary source, only by the one owner comment above.
- Whether the system-board end of the Compaq diskette cable is a standard 34-pin header (so a generic cable fits) was not found.

## 3. The floppy interface as a data channel from the Pi

### Takeaway
A Pi Zero W in mass-storage gadget mode is a proven stand-in for the GoTEK's USB stick, but the image must not be edited underneath FlashFloppy: detach, change, re-attach. Expect roughly 25-45 KB/s from a 1.2 MB "disk" (estimate; ceiling 46 KB/s), which beats a 115200-baud serial link several times over. No ready-made Wi-Fi floppy emulator for PCs was found.

### Cited Findings

Pi Zero as the USB stick
- A Pi Zero exposing a disk image to a FlashFloppy GoTEK works with `dtoverlay=dwc2` in config.txt and `modules-load=dwc2,g_mass_storage g_mass_storage.file=/root/zerodisk.img` on the kernel command line. Measured in that setup: 512-byte writes took 2.5-4 microseconds and 2 kB reads 6-10 microseconds on the Pi side, with USB Full Speed (12 Mbit/s) the main limit. The author proposes (untested) `rmmod g_mass_storage`, edit the image, `modprobe g_mass_storage` to change contents over Wi-Fi. — [FlashFloppy discussion #451](https://github.com/keirf/flashfloppy/discussions/451)
- In the same thread another user serves a FAT partition (not a file) from a Pi Zero W to a BBC Master's GoTEK and copies images in over SCP, saying the Pi and GoTEK can both access it "with some limits". — [FlashFloppy discussion #451](https://github.com/keirf/flashfloppy/discussions/451)
- The Linux gadget documentation is explicit: "if a file is used as a backing storage, it may not be modified by any other process. This is because the host assumes the data does not change without its knowledge." — [Linux kernel: Mass Storage Gadget](https://github.com/torvalds/linux/blob/master/Documentation/usb/mass-storage.rst)
- The gadget supports swapping media without unloading: with `removable=1` the unit accepts eject; each logical unit has sysfs entries `file` (write a new path to change the backing file), `ro`, `nofua`, and `forced_eject` (any write detaches the backing file "regardless of whether the host has allowed it"). — [Linux kernel: Mass Storage Gadget](https://github.com/torvalds/linux/blob/master/Documentation/usb/mass-storage.rst)
- A Raspberry Pi forum user reports a FlashFloppy GoTEK reads and writes a Pi Zero W gadget only after adding `removable=1`; without it the storage looked read-only. (Snippet only.) — [Raspberry Pi Forums: Pi Zero W Mass Storage How to Make Writable](https://www.raspberrypi.org/forums/viewtopic.php?t=213309)
- ADF On-The-Go is a complete Pi Zero + GoTEK product for the Amiga: a web UI and REST API that build "virtual USB drives" from images and swap them "without ever disconnecting the USB cable from your Gotek". It needs Raspberry Pi OS 12+, Python 3, mtools and passwordless sudo, and has no network security. — [adfotg README](https://github.com/Zalewa/adfotg)
- adfotg warns: cut or block the +5 V line in the USB cable between the Pi and the GoTEK, otherwise the Pi back-powers the GoTEK and the computer when the computer is off, and the Pi reboots. — [adfotg README](https://github.com/Zalewa/adfotg)
- Another project keeps the gadget's backing store on a network share; its author notes a Pi in gadget mode can no longer act as a USB host. (Snippet only.) — [DanBuchan/Networked_USB_Mass_Storage](https://github.com/DanBuchan/Networked_USB_Mass_Storage)

How FlashFloppy caches
- Since v2.5a FlashFloppy has a "fragment-offsets cache implemented at the FAT filesystem layer" and a "block cache implemented at the mass-storage volume layer"; v3.32 gave IMG/DSK "more space for mass-storage block cache"; v3.34 made the AT32F435 "cache HFE and QD image data, since there is plenty of RAM"; v3.42 streams large sector writes to flash. — [FlashFloppy RELEASE_NOTES](https://github.com/keirf/FlashFloppy/blob/master/RELEASE_NOTES)
- FlashFloppy responds to the USB stick being pulled, and re-selects the last image at start (`image-on-startup = last`, recorded in IMAGE_A.CFG on the stick). — [FlashFloppy RELEASE_NOTES](https://github.com/keirf/FlashFloppy/blob/master/RELEASE_NOTES); [FlashFloppy examples/FF.CFG](https://raw.githubusercontent.com/keirf/FlashFloppy/master/examples/FF.CFG)
- FlashFloppy keeps an HxC-style "Direct Access mode" reachable by stepping to cylinder 255 (`max-cyl = 255` "is required for access to Direct Access mode as used by image-selector utilities and Autoswap games"). — [FlashFloppy examples/FF.CFG](https://raw.githubusercontent.com/keirf/FlashFloppy/master/examples/FF.CFG)
- In `interface = ibmpc` mode pin 34 carries disk-change, reset by a step pulse (`chgrst = step`). — [FlashFloppy examples/FF.CFG](https://raw.githubusercontent.com/keirf/FlashFloppy/master/examples/FF.CFG)

Other network-behind-floppy projects
- ethflop is a DOS TSR that emulates a floppy drive from an image on a Linux server over raw Ethernet frames: DOS 2.x+, 8088+, under 2 KiB resident, virtual floppies from 360 K to 31 MB, server run as root (`./ethflopd eth0 /var/floppies`), ISC licence. It needs "some kind of Ethernet adapter (physical or emulated, for example through PLIP) and a suitable packet driver", on the same LAN segment. It involves no floppy hardware at all. — [ethflop documentation](http://ethflop.sourceforge.net/ethflop.txt)
- ethflop cannot simply take B: on a single-floppy machine, because DOS maps a phantom B: onto A:; the author's workaround is to declare a non-existent second drive in the BIOS. — [ethflop documentation](http://ethflop.sourceforge.net/ethflop.txt)
- A web search for ESP32- or Pico-based 34-pin floppy emulators with Wi-Fi found none aimed at PCs: Adafruit's RP2040 floppy board (34-pin, no network), FujiNet (ESP32, network images, but Atari SIO and other 8-bit buses), and commercial Ethernet units (emufdd ETH, FLOPPYFlash). — [Adafruit floppy board coverage](https://tech.yahoo.com/general/articles/adafruit-designs-raspberry-pi-pico-142033973.html); [FujiNet firmware](https://github.com/FujiNetWIFI/fujinet-platformio); [emufdd ETH hardware manual](https://embeddedsw.net/doc/emufdd_ETH_hw_manual.pdf)

Floppy speed
- The 1.2 MB format spins at 360 RPM with a 500 kbit/s data rate. — [cctalk: Fred Cisin on diskette formats](https://classiccmp.org/pipermail/cctalk/2016-June/024346.html)

### Inferences
- Throughput ceiling (arithmetic, not a measurement): 15 sectors x 512 bytes x 6 revolutions/s = 46,080 bytes/s if every revolution yields a full track. Under FlashFloppy's `host = pc-dos` (300 RPM) the ceiling is 38,400 bytes/s. A whole 1.2 MB image is 160 tracks, so 27-32 s at best. DOS 3.1 reading file by file through the BIOS will lose some revolutions; my estimate for sustained reads is **25-45 KB/s**, about 2-4 times a 115200-baud serial link (11.5 KB/s) and 7-12 times 38400 baud. FlashFloppy's `track-change = instant` removes seek time, which should put it near the top of that range.
- Live changes: because FlashFloppy caches FAT fragment offsets and blocks, and the kernel doc forbids modifying an attached backing file, the safe cycle is (1) Pi writes `forced_eject` (or clears `file`), (2) Pi rewrites the 1.2 MB image inside the FAT backing file with mtools, (3) Pi writes the backing file path back to `file`. FlashFloppy then sees a stick removal and insertion, remounts the last image, and asserts disk-change on pin 34, so DOS rereads the directory on next access. Expected swap time: a few seconds (estimate; not measured anywhere I found).
- That gives a one-directional "sneakernet without the sneakers": 1.2 MB per swap, both ways (the Compaq can write to the image; the Pi reads it after ejecting). It is a bulk channel, not a stream: fine for delivering Wolfenstein, Word or Doom8088 files in several disk-loads, not for live video.
- Power and boot order: if the Zero W is powered from the GoTEK's USB port it boots only after the Compaq is switched on, tens of seconds too late to boot DOS from the "floppy". Powering the Zero separately means following adfotg's advice and isolating the USB +5 V line. My reasoning from the adfotg warning.
- The Pi 3 B+ cannot be the gadget itself (the task brief already assigns that role to the Zero W); the Zero W would fetch files from the 3 B+ over Wi-Fi.
- ethflop and EtherDFS speak raw Ethernet frames, and SLIP carries only IP, so neither can run over the existing serial cable even with EtherSLIP faking an Ethernet interface. They become options only with a real Ethernet path (for example a parallel-port Ethernet adapter). My reasoning; the ethflop home page summary I retrieved mentioned SLIP alongside PLIP, but the documentation file names only PLIP.

### Gaps
- No statement from FlashFloppy's author on exactly when cached blocks are discarded, or whether an in-place change to an image's data blocks would be noticed without a re-insert. Needs a test.
- No measured BIOS-level read rate (KB/s) for a 1.2 MB floppy or a GoTEK on a 286 was found. The figures above are arithmetic and estimate.
- No DOS program that uses FlashFloppy's direct-access mode (cylinder 255) on a PC was found; the known clients are for Amiga, Atari ST and CPC. Whether a PC floppy controller can be driven to cylinder 255 for this was not investigated.
- HxC's USB-streaming emulator and any Pi-compatible host software for it were not researched.
- Whether the GoTEK's USB port can supply a Zero W's peak current was not found.

## 4. The hard disk: original drives, the BIOS type table, CF/SD adapters, and the SETUP disk

### Takeaway
"Type 2" is Compaq's 20 MB drive (615 cylinders, 4 heads, 17 sectors) with an integrated controller, supported from ROM K. A CompactFlash-to-IDE adapter is a known-good replacement in this machine; owners report Type 42 (504 MB) working, one restorer could only get Type 4 (68 MB) to work, so card choice matters. The drive type lives in CMOS and can only be changed with Compaq's SETUP program, which is run from a diagnostics diskette or from the DOS prompt.

### Cited Findings

Original drives
- Compaq's fixed-disk list for the Portable III (rows reconstructed from jumbled OCR): 20 MB, **Type 2**, interleave 1:1, integrated controller, minimum ROM K, spare 107890-001; 20 MB, **Type 2**, interleave 3:1, integrated, ROM K, spare 107358-001; 40 MB, **Type 17**, interleave 3:1, integrated, ROM K, spare 107357-001; 40 MB, **Type 43**, interleave 1:1, integrated, minimum ROM **P**, spare 114106-001, footnoted as needing a later MS-DOS (version garbled in OCR). A 40 MB DC2000 tape drive is listed for the expansion unit only. — [Compaq Service Quick Reference Guide, Portable III pages](https://www.minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Information%20from%20the%20CSQRG.pdf)
- Model 1 had no hard disk, Model 20 a 20 MB disk ($4,999), Model 40 a 40 MB disk ($5,799); the machine shipped with MS-DOS 3.1. — [Wikipedia: Compaq Portable III](https://en.wikipedia.org/wiki/Compaq_Portable_III)
- The hard disk is "a 3.5-inch ATA hard drive on a shock-absorbing mount". — [John Elliott: Compaq Portable III](https://www.seasip.info/VintagePC/compaq3.html)
- Restorers describe the original drives as Conner: "Most of these machines came with different-sized Connor hard drives which are notoriously rubbish ... even when you sort that out, they generally don't work"; another owner's original 20 MB disk, believed to be a Conner, still worked. — [Ret.rocks](https://ret.rocks/index.php/one-off-works/compaq-portable-iii); [OldSilicon: Compaq Portable III](https://www.oldsilicon.com/compaq-portable-iii)
- Conner's CP-342 is a 40 MB IDE drive "very similar to Conner's original Compaq-specific model, the CP-341"; its firmware identifies itself as CP-341. — [OS/2 Museum: Can This Conner Talk?](https://www.os2museum.com/wp/can-this-conner-talk/)
- SW1 on the system board (positions reconstructed from OCR order): switches 1-2 base memory (256/512/640 KB), 3-4 expansion memory module type, **5 ON = enable fixed disk drive (default), OFF = disable**, 6 CPU boot speed (ON 8 MHz, OFF 12 MHz default), 7 plasma display CGA or monochrome mode, 8 reserved. Jumpers also select fixed-disk primary or secondary address. — [Compaq Service Quick Reference Guide, Portable III pages](https://www.minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Information%20from%20the%20CSQRG.pdf)

The drive type table
- "The BIOS supports only predefined drive geometries; if you want to use anything else, you'll need to use a disk manager overlay." Table from a revision K ROM (cylinders/heads/sectors, capacity): 1 306/4/17 10.2 MB; **2 615/4/17 20.4 MB** (landing zone 638, precomp 128); 3 615/6/17 30.6; 4 1024/8/17 68.0; 5 940/6/17 46.8; 6 697/5/17 28.9; 7 462/8/17 30.7; 8 925/5/17 38.4; 9 900/15/17 112.1; 10 980/5/17 40.7; 11 925/7/17 53.7; 12 925/9/17 69.1; 13 612/8/17 40.6; 14 980/4/17 32.5; 15 unused; 16 612/4/17 20.3; **17 980/5/17 40.7**; 18 966/6/17 48.1; 19 1023/8/17 67.9; 20 733/5/17 30.4; 21 733/7/17 42.6; 22 805/6/17 40.1; 23 924/8/17 61.4; 24 966/14/17 112.3; 25 966/16/17 128.3; 26 1023/14/17 118.9; 27 966/10/17 80.2; 28 748/16/17 99.3; 29 805/6/26 61.3; 30 615/4/25 30.0; 31 615/8/25 60.1; 32 905/9/25 99.4; 33 748/8/34 99.3; 34 966/7/34 112.3; 35 966/8/34 128.3; 36 966/9/34 144.3; 37 966/5/34 80.2; 38 611/16/63 300.7; 39 1023/11/33 181.3; 40 1023/15/34 254.8; 41 1023/15/33 247.3; **42 1023/16/63 503.5 MB (the largest)**; **43 805/4/26 40.9**; 44 805/2/26 20.4; 45 748/8/33 96.4; 46 748/6/33 72.3; 47 966/5/25 59.0. — [John Elliott: Compaq Portable III](https://www.seasip.info/VintagePC/compaq3.html)
- Conflict: Elliott's table, from a ROM he identifies as revision K, includes Type 43, while Compaq's parts list gives ROM P as the minimum for the Type 43 drive. — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html); contradicted by [Compaq Service Quick Reference Guide](https://www.minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Information%20from%20the%20CSQRG.pdf)

CF and SD adapters in this machine
- OldSilicon: StarTech IDE2CF adapter with a 4 GB CF card set as **Type 42**, "the largest disk type the Compaq BIOS recognized", so about 500 MB usable; held in a 3D-printed bracket in the drive sled. No freezes or master/slave problems mentioned. — [OldSilicon: Compaq Portable III](https://www.oldsilicon.com/compaq-portable-iii)
- Stillwell Labs sold a ready-made kit ($74, shown out of stock): IDE-to-CF adapter in a colour-matched mount, SanDisk 4 GB CF, "configured as a Type 42 hard drive", booting MS-DOS 6.22 with about 500 MB; "configuration ... is done via a boot floppy disk". — [Tindie: Compaq Portable III Compact Flash SSD Hard Drive](https://www.tindie.com/products/stillwell/compaq-portable-iii-compact-flash-ssd-hard-drive/)
- Ret.rocks, across several machines: "I could only get these Compaqs to work correctly with **Type 04** drive setup" (about 70 MB); other types gave "error!" at boot after FDISK and FORMAT /S. He uses 1 GB Pretec cards and says the card "must be of the 'industrial' and 'fixed' variety". — [Ret.rocks](https://ret.rocks/index.php/one-off-works/compaq-portable-iii); contradicted on Type 42 by [OldSilicon](https://www.oldsilicon.com/compaq-portable-iii) and [Stillwell Labs](https://www.tindie.com/products/stillwell/compaq-portable-iii-compact-flash-ssd-hard-drive/)
- One Portable III owner's CF adapter "worked perfectly for a few minutes, then it froze", and he moved to an SD-based IDE adapter. (Snippet only.) — [rclassiccomputers: Compaq Portable III](https://rclassiccomputers.com/2017/08/08/portableiii/)
- General 286 experience: on a Phoenix 286 BIOS with no user-defined type, CF cards entered as the nearest predefined type booted partway and then gave read errors; other posters report that "most IDE devices will adjust to whatever geometry you enter as long as you don't make the size larger than the device can handle", that cards presenting as removable media fail on old systems, and that industrial cards work most often. (Snippets only.) — [Vogons: CompactFlash Trouble in 286 Land](https://www.vogons.org/viewtopic.php?t=58446); [Vogons: How to set up CF cards on 286-486](https://www.vogons.org/viewtopic.php?t=55167); [VCFed: IDE-to-CompactFlash adaptor boards](https://forum.vcfed.org/index.php?threads/getting-one-of-those-ide-to-compactflash-adaptor-boards-to-work.79472/)
- Old-BIOS CHS limit is 1024 cylinders, 16 heads, 63 sectors, about 528 MB. — [retrocmp: CompactFlash](https://retrocmp.de/hardware/cf-dom/cf-dom.htm)
- XTIDE on this machine: the stock BIOS "only checks from C000 - DF80h for extension roms", and one owner patched the system ROM to change that so an XTIDE ROM could be used. (Snippet only; thread not readable.) — [Vogons: Compaq Portable III modded BIOS / XTIDE](https://www.vogons.org/viewtopic.php?t=62482)

SETUP and diagnostics disk
- "The BIOS setup is not stored in ROM so you have to boot from a Compaq Diagnostic Diskette to get into the settings." With no battery, settings last about ten minutes; with the machine plugged in they are kept. Two battery types exist: an early 4-terminal 3 V module (107157-001 per Ret.rocks) and a later 3-pin 3.6 V lithium. — [Ret.rocks](https://ret.rocks/index.php/one-off-works/compaq-portable-iii)
- Compaq's battery spares: 107385-001 for system board 000709-001 and battery/clock module 107872-001 for board 000709-003. — [Compaq Service Quick Reference Guide, Portable III pages](https://www.minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Information%20from%20the%20CSQRG.pdf)
- The diagnostics were distributed by Compaq (later HP) as SoftPaqs: **SP0316** makes 360 KB 5.25-inch disks and **SP0308** a 720 KB 3.5-inch disk. They contain SETUP, INSPECT and TEST, "version 8.00 DP256, for Discontinued Products with at least 256k memory". Running the self-extractor and then QRST.EXE writes the disk. (Snippets only.) — [Vogons post 1366880](https://www.vogons.org/viewtopic.php?p=1366880); [WinWorld forum](https://forum.winworldpc.com/discussion/comment/138981); [OldSilicon](https://www.oldsilicon.com/compaq-portable-iii)
- The SP0308 disk is not bootable on its own; boot DOS first, then run SETUP.EXE from the diagnostics disk. Ret.rocks gives the same workaround for 1.44 MB drives ("get out to command prompt, switch to the BIOS setup floppy disk and run setup from there"). (Vogons: snippet only.) — [Vogons post 1225549](https://www.vogons.org/viewtopic.php?p=1225549); [Ret.rocks](https://ret.rocks/index.php/one-off-works/compaq-portable-iii)
- Generic AT setup disks can set drives but leave a CMOS checksum error, because Compaq used its own checksum. (Snippet only.) — [classiccmp: Dave Dunfield](https://www.classiccmp.org/mailman3/hyperkitty/list/test-drb@ccmp.vtda.org/message/SXYQZUTTWUO5I5EYV6RM2XDAGNELZPK6/)
- Stillwell Labs sells a set of six physical 5.25-inch system and boot disks for the Portable III/386. — [Tindie: Compaq Portable III/386 System/Boot disks](https://www.tindie.com/products/stillwell/compaq-portable-iii386-systembootdisks-6-disks/)

### Inferences
- Try the original drive first: it is labelled Type 2, CMOS is presumably already set to Type 2, and reconnecting it costs nothing. Restorers' experience says to expect failure.
- For a CF or SD adapter under MS-DOS 3.1, the simplest choice is to leave CMOS at **Type 2** and let the card present 615/4/17 (20 MB). No SETUP run is needed, and the original drive can go back in unchanged. A 30 MB type (Type 3, 615/6/17) is the largest that MS-DOS 3.1 can fully use as one partition (see question 5), but it needs SETUP.
- Type 42 (504 MB) is worth having only with a DOS that handles partitions over 32 MB. Given the Type 42 versus Type 4 conflict between owners, buy an industrial, fixed-disk-mode CF card of 512 MB to 4 GB, and plan to test Type 2 first, then Type 42, then Type 4.
- Whether a card honours a BIOS-chosen geometry depends on the card accepting the drive-parameter command the BIOS sends; that is the likely reason some cards work with any type and others only with some. General ATA knowledge; I found no source that tests this on a Compaq.
- Jumper the adapter as master with nothing else on the cable.
- SP0316 produces 360 KB images, which are the unreliable case on a GoTEK in a 1.2 MB-configured AT (question 1). The cleaner route is to copy the SETUP files onto a 1.2 MB DOS boot image and run SETUP from the prompt. Ret.rocks claims the setup disk cannot simply be file-copied; the Vogons posters say running SETUP.EXE from DOS works. Unresolved until tried.
- Legitimacy: SP0308 and SP0316 were free support downloads from Compaq and then HP for owners of these machines. HP's FTP links in the forum posts date from 2020-2025 and I could not confirm any official host is still live; the copies on archive.org and minuszerodegrees.net are unofficial mirrors of a vendor support download, not something the vendor has released as free software.
- The archive.org ROM dumps (K, P.2, R.2) are Compaq-copyright firmware uploaded by a user with no rights statement. Reading them to identify a revision is one thing; burning a newer revision into this machine is a licensing grey area and should be described that way.

### Gaps
- The make and model of the 20 MB Type 2 drive is not stated in any primary source found. "Conner" comes from restorers. One blog calls the original a 2.5-inch Conner, which conflicts with Elliott's "3.5-inch".
- No source confirms a specific SD-to-IDE adapter model in a Portable III.
- The Vogons modded-BIOS thread could not be read, so how XTIDE was fitted (patched system ROM, expansion unit card, or the board's second ROM set) is unknown. Compaq's jumper list does mention "Enable ROM set 2 / Disable ROM set 2" and "16-KB ROM / 32-KB ROM"; what ROM set 2 is, and its address, was not found.
- Which diagnostics version is right for ROM K versus later ROMs was not found.

## 5. DOS limits and options

### Takeaway
MS-DOS 3.1 cannot use more than 32 MB per hard-disk volume. Compaq DOS 3.31 was the first DOS to break that limit but is not free. FreeDOS and SvarDOS are free and run on 8086-class machines with 640 KB; mTCP NetDrive works with any of them, including MS-DOS 3.1.

### Cited Findings
- PC-DOS/MS-DOS 3.10 had a 32 MB limit for a hard-disk volume; larger physical drives were split into several DOS drives. — [classiccmp: Fred Cisin (2014)](https://www.classiccmp.org/mailman3/hyperkitty/list/test-drb@ccmp.vtda.org/message/OYGEUUYBUYLTIKJNHGDJNYB7HBF3QJSU/)
- Compaq's MS-DOS 3.31 "pioneered support for 32-bit logical sector numbers and thus partitions larger than 32MB"; the same support reached everyone else in DOS 4.0. Compaq released several revisions of 3.31. (Snippets only.) — [OS/2 Museum: DOS 3.3](https://www.os2museum.com/wp/dos/dos-3-3/); [PCjs blog 2018-01-27](https://pcjs.org/blog/2018/01/27)
- Compaq itself tied the Portable III's 1.44 MB drive to MS-DOS 3.31 (revision A as drive B, revision B as drive A). — [Compaq Service Quick Reference Guide, Portable III pages](https://www.minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Information%20from%20the%20CSQRG.pdf)
- One Portable III arrived running Compaq DOS 3.3; CF conversions are sold and shared with MS-DOS 6.22. — [OldSilicon](https://www.oldsilicon.com/compaq-portable-iii); [Tindie: Stillwell Labs](https://www.tindie.com/products/stillwell/compaq-portable-iii-compact-flash-ssd-hard-drive/)
- FreeDOS's stated requirement is a PC/XT with 640 kB; its original spec says it "should operate on processors as low as the 8088 (XT) with as little memory as 640k". FreeDOS 1.4 has a floppy-only edition for the PC, XT and AT with 720 KB, 1.2 MB and 1.44 MB images. (Snippets only.) — [Wikipedia: FreeDOS](https://en.wikipedia.org/wiki/FreeDOS); [FreeDOS 1999 spec](https://help.freedos.org/docs/about/fdspec.html); [Computer Hope: FreeDOS](https://www.computerhope.com/jargon/f/freedos.htm)
- On a 286, FreeDOS's EMM386 and HIMEM do not work; FDXMS286 provides XMS and the HMA where extended memory exists. (Snippets only.) — [Vogons post 414854](https://www.vogons.org/viewtopic.php?p=414854); [Eric Auer: FreeDOS memory FAQ](https://www.auersoft.eu/soft/specials/memfaq.txt)
- SvarDOS runs on 8086/8088 machines, ships as four 360 kB images or one 1.44 MB image, and switched its default kernel from FreeDOS's to the open-source EDR-DOS kernel with release 20240915; kernels are swappable packages. (Snippets only.) — [The Register: SvarDOS, DR-DOS reborn](https://www.theregister.com/2024/12/23/svardos_drdos_reborn/); [bttr-software forum: SvarDOS announcement](https://www.bttr-software.de/forum/forum_entry.php?id=22095)
- mTCP NetDrive: "A single device driver works with all versions of DOS starting with DOS 2.0"; "DOS versions with FAT16B support can use remote images up to 2GB in size. (FAT12 and FAT16 are limited to 32MB images.)" — [mTCP NetDrive](http://brutmanlabs.org/mTCP/mTCP_NetDrive.html)

### Inferences
- With MS-DOS 3.1 and one hard disk, plan on a single partition of at most 32 MB. Extended partitions with logical drives arrived with DOS 3.3, so under 3.1 the rest of a larger CF card is simply unused. Recalled, not sourced in this session.
- Microsoft published MS-DOS 4.00 source and binaries under the MIT licence in April 2024 (github.com/microsoft/MS-DOS). That would be a legitimately free Microsoft DOS with over-32 MB partition support. I am recalling this and did not verify it today; it also has a reputation for bugs and a larger memory footprint.
- This machine has 640 KB and (as described) no extended memory, so no DOS can load itself high. FreeDOS's kernel and shell will leave noticeably less conventional memory than MS-DOS 3.1; one forum report of about 491 KB free under FreeDOS is unverified. For memory-hungry programs (Word 5.5, Doom8088) staying on MS-DOS 3.1 or moving to SvarDOS with the EDR kernel is the safer bet. Estimate.
- Compaq DOS 3.31 is the period-correct fix for both the 32 MB limit and 1.44 MB support, but it is commercial software. Use it only if an original copy is owned.
- Microsoft Word 5.5: Microsoft released it as a free download in the late 1990s as a year-2000 fix. Recalled, not verified today; confirm the current terms before calling it free.

### Gaps
- No measured conventional-memory figures for FreeDOS 1.4 or SvarDOS on a 640 KB 286 were found.
- No report of FreeDOS or SvarDOS specifically on a Portable III was found.
- Whether FreeDOS's FAT16B handling works with this BIOS's fixed drive types (for example Type 42) is untested in the sources.

## 6. Storage served by the Pi over a link (NetDrive, EtherDFS, ethflop, XTIDE serial drive, INTERLNK, serial block drivers)

### Takeaway
mTCP NetDrive is the only option that works today over the existing serial cable with MS-DOS 3.1 and a Pi-hosted server: a drive letter backed by an image on the Pi, limited by the serial line to roughly 8-10 KB/s at 115200 baud (estimate). EtherDFS and ethflop need real Ethernet. The XTIDE serial drive needs an option ROM this machine cannot easily host. INTERSVR has no non-DOS implementation.

### Cited Findings

mTCP and NetDrive
- Current mTCP is dated **2026-10-10**: "adds black and white Sixel graphics to Telnet, makes Ping more accurate, and has major performance improvements for NetDrive"; EtherSLIP was updated with two bug fixes on 2026-04-13; mTCP has been on GitHub since 2026-06-29. — [mTCP home page](http://brutmanlabs.org/mTCP/mTCP.html)
- mTCP needs an 8088 or better, 96-384 KB of memory depending on the program, DOS 2.1 or newer, and a packet driver that is Ethernet or emulates Ethernet; packet drivers exist for "serial ports using SLIP, Compressed SLIP, or PPP connections". — [mTCP home page](http://brutmanlabs.org/mTCP/mTCP.html)
- NetDrive is "a DOS device driver that allows you to access a remote disk image hosted by another machine as though it was a local device with an assigned drive letter"; the driver "uses less than 9KB of RAM (add another 5 to 25KB depending on your Ethernet card)"; the server "runs on Windows (10 or 11), Linux, macOS and FreeBSD. No special permissions are needed"; "the protocol uses UDP"; images are "standard raw disk images that can be manipulated using Linux tools"; several drives can be mounted at once; a checkpoint feature gives undo. Other TCP/IP programs can share the network device while NetDrive is active. — [mTCP NetDrive](http://brutmanlabs.org/mTCP/mTCP_NetDrive.html)
- Server binaries include Linux ARM, 32-bit and 64-bit. (Snippet only.) — [Vogons: mTCP NetDrive thread](https://www.vogons.org/viewtopic.php?p=1218111)
- 2026-10-10 changes: read-ahead when DOS reads several blocks at once, and "large writes" using IP fragments for writes over 1 KB; "a fast 386 class machine saw read speeds improve by 2.5x on a local network and 20x when connected to a remote server". The pass-through packet driver now supports non-mTCP programs. — [mTCP 2026-10-10 release notes](http://brutmanlabs.org/mTCP/mTCP_2026-10-10_Release_Notes.html)
- Earlier Ethernet figures from the author: about 88 KB/s on a PCjr with a WD8003, 130 KB/s on a PS/2 Model 25, about 380 KB/s on a 386-40 with a 10 Mbit card. NetDrive's default MTU of 576 avoids fragments and suits SLIP and PPP users. The new DOS driver needs the new server; old drivers work with new servers. (Snippets only.) — [Vogons: mTCP NetDrive thread, page 5](https://www.vogons.org/viewtopic.php?t=97743&start=80); [mTCP documentation PDF, 2025-01-10](https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/net/mtcp/2025-01-10/mTCP_2025-01-10.pdf)

EtherDFS and ethflop
- EtherDFS is a DOS installable-filesystem TSR that maps a remote (typically Linux) directory to a drive letter "using raw ethernet frames"; it needs only a packet driver. — [EtherDFS home page](http://etherdfs.sourceforge.net/)
- EtherDFS runs on 8086 and up, uses about 7 K (loadable high), and gained MS-DOS compatibility at v0.7; a fork, EtherDFS-3, targets DOS 3.20 and 3.30. The Linux server, ethersrv-linux, must run as root (`ethersrv-linux eth0 /path`). (Snippets only.) — [VCFed: EtherDFS thread](https://www.vcfed.org/forum/forum/genres/pcs-and-clones/57837-etherdfs-an-ethernet-drive-for-dos?p=699693); [SlackBuilds: ethersrv-linux](https://slackbuilds.org/repository/15.0/network/ethersrv-linux/)
- ethflop: DOS 2.x+, 8088+, 4 K of RAM to load and under 2 KiB resident, raw Ethernet to a Linux daemon run as root, same LAN segment, floppies from 360 K to 31 MB, one client per writable image; TSR version 20240920. — [ethflop documentation](http://ethflop.sourceforge.net/ethflop.txt); [ethflop home page](http://ethflop.sourceforge.net/)

XTIDE Universal BIOS serial drive
- The XUB serial-drive feature requires an XTIDE Universal BIOS option ROM on the client and a COM port; the server program SerDrive serves flat floppy or hard-disk images (default a 32 MB image, CHS 65/16/63), defaults to 9600 baud, and is documented for Windows XP or later. The client finds it by holding Alt during detection or pressing F6; it needs MODULE_SERIAL (and MODULE_SERIAL_FLOPPY for floppies), which the 4 KB "tiny" build lacks. (Snippet only; older wiki revision.) — [XTIDE Universal BIOS wiki: SerialDrives](https://xtideuniversalbios.org/export/368/xtideuniversalbios/wiki/SerialDrives.wiki)
- XUBDisk is a boot floppy that loads the XTIDE Universal BIOS into RAM, scans controllers at 300h, 1F0h and 170h, and boots the first hard disk found; the BIOS stays in memory for the session. (Snippet only.) — [Vogons: XUBDisk](https://www.vogons.org/viewtopic.php?t=98183)
- The Portable III BIOS scans only C000-DF80h for option ROMs. (Snippet only.) — [Vogons: Compaq Portable III modded BIOS / XTIDE](https://www.vogons.org/viewtopic.php?t=62482)

INTERLNK and serial block drivers
- Interlnk consists of the INTERLNK.EXE client driver and the INTERSVR.EXE server; the server is a DOS program that takes over its machine. Forum consensus is that nobody has produced an INTERSVR emulator for Unix. (Snippets only.) — [Wikipedia: Interlnk](https://en.wikipedia.org/wiki/Interlnk); [Vogons: Modern options/alternatives for Interlnk?](https://www.vogons.org/viewtopic.php?t=53126); [bttr-software: open source replacement of INTERLNK and INTERSVR](https://www.bttr-software.de/forum/board_entry.php?id=20392)
- serialfd is the closest existing "disk over serial with a Linux server": a DOS TSR in assembly that "will intercept BIOS int 13h calls, forward these over the serial port and wait for the response", a Linux C program that serves sectors from a floppy image, and a boot stub (`sfdboot.asm`) for bootable images. — [kobolt/serialfd](https://github.com/kobolt/serialfd)
- Compaq listed a "2nd Serial" option board for the Portable III, with jumpers assigning serial devices to COM1/IRQ4 or COM2/IRQ3. — [Compaq Service Quick Reference Guide, Portable III pages](https://www.minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Information%20from%20the%20CSQRG.pdf)

### Inferences
- NetDrive over SLIP is line-limited. At 115200 baud the wire carries 11.5 KB/s; after IP, UDP and NetDrive headers and request/response turnaround I estimate 8-10 KB/s of file data, and about 3 KB/s at 38400. No measurement over SLIP was found. On real Ethernet a 12 MHz 286 should land between the PS/2 Model 25 figure (130 KB/s) and the 386-40 figure (380 KB/s). Estimate.
- Ranking by speed for this machine as it stands (all estimates): GoTEK 1.2 MB images 25-45 KB/s in 1.2 MB lumps; NetDrive over 115200 SLIP 8-10 KB/s but any size up to 32 MB and always live; Kermit transfers below that. The GoTEK is the faster bulk loader; NetDrive is the convenient live drive.
- Under MS-DOS 3.1 a NetDrive image must be FAT12 or FAT16 and at most 32 MB (from the NetDrive page's FAT16B statement). That is still larger than the original 20 MB disk, and several can be mounted at once.
- Memory cost on the Compaq: under 9 KB for NetDrive plus the EtherSLIP packet driver. The serial port is then shared between SLIP and anything else, so it takes turns with Kermit unless a second serial port is fitted.
- EtherDFS and ethflop are ruled out on the serial cable (raw Ethernet frames cannot cross SLIP) and stock EtherDFS's support for MS-DOS 3.1 is doubtful, given that a separate fork exists for DOS 3.2/3.3. They become relevant only if an Ethernet adapter is added; ethflop would then give a 31 MB "floppy" for 2 KB of memory.
- XTIDE serial drive: without an expansion unit there is no socket for an option ROM, the documented server is Windows-only, and whether a floppy-loaded XUB (XUBDisk) includes or can be configured for the serial module is unconfirmed. Not a practical path now.
- INTERLNK: the client is a commercial MS-DOS 6 component and there is no Linux server. Running INTERSVR inside an emulator on the Pi with the serial port passed through is conceivable but I found nobody doing it; not recommended.
- serialfd works at the BIOS level (INT 13h), so it could in principle present a Pi-hosted floppy image, even a bootable one, over the existing cable with no network stack. Its baud rate, DOS-version requirements, licence and maturity were not established; it would be an experiment.

### Gaps
- No measured NetDrive throughput over SLIP or on any 286 was found.
- The NetDrive documentation PDF for 2026-10-10 was not read; exact DOS-side requirements for the new read-ahead driver (memory, MTU) come from the summary pages only.
- EtherDFS's own documentation file returned 404, so its minimum DOS version and current release were not confirmed from the primary source.
- The XTIDE and XUBDisk pages on Vogons could not be opened; whether a Linux build of SerDrive exists was not checked.
- No DOS block-device driver that mounts a hard-disk image (rather than a floppy at INT 13h) over a plain serial port with a Linux server was found.
- Whether Kermit and a SLIP packet driver can alternate on one COM port without a reboot was not researched here (it belongs with the links research).
