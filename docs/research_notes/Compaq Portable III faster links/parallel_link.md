# Parallel-port data link between the Compaq Portable III and a Raspberry Pi 3 B+

Research pass of 2026-10-13. Every line under "Cited Findings" is sourced (URL given). Every line under "Inferences" is my estimate or reasoning. "Gaps" lists what could not be found or fetched. Fetch problems this pass: Vogons threads and eBay sold-listing pages blocked direct fetching (bot wall / HTTP 403), so Vogons and eBay items below come from search-result snapshots and are flagged as such.

Corrections to `docs/graphics-research.md` found in this pass:
- "Pi GPIO to the parallel port ... No ready-made project" is wrong. Two ready-made Pi parallel-port boards exist with Linux `parport` drivers (open-hardware pi-parport; Elesar S&P HAT, on sale at GBP 38.40). What does not exist is a documented PLIP or LapLink link running over them.
- "Xircom PE3-10BT, used, about $40-150" is too low for 2026 asking prices. eBay asking prices seen: $95 to $382. Sold prices could not be retrieved.
- "mTCP measured 23-53 KB/s receive on 8088/8086s" is confirmed (22.8 and 53.1 KB/s), and those two figures are both on standard, output-only ports. Send on the same machines was 42.9 and 87.5 KB/s.
- "whether [the parallel port] is bidirectional is unknown" stays unknown. Compaq's Operations Guide gives no register-level detail.

## 1. Is the Portable III's parallel port output-only (SPP) or bidirectional?

### Takeaway
No document found says. Compaq's own guide calls it only "a standard 25-pin parallel interface for connecting a printer", so plan for an output-only SPP port (8 bits out, 5 status bits in) and run a two-minute direction-bit test on the real machine before buying anything that needs 8-bit input.

### Cited Findings
- Compaq's Operations Guide lists three rear connectors: "A 9-Pin RGBI Interface Connector", "A 9-Pin Asynchronous Communications (Serial) Interface", "A 25-Pin Parallel Interface". Its glossary defines the parallel interface as "A standard 25-pin parallel interface for connecting a printer." No mention of bidirectional operation, port address or IRQ anywhere in the OCR text (searched for parallel, bidirectional, LPT1, Centronics). — [Compaq Portable III Operations Guide, archive.org](https://archive.org/details/compaq-portable-3-operations-user-manual)
- The same guide describes an optional "Asynchronous Communications/Parallel Printer Board" for the expansion unit whose parallel interface "can be configured as LPT1, LPT2, LPT3, or disabled". — [Operations Guide](https://archive.org/details/compaq-portable-3-operations-user-manual)
- The keyboard attaches by "a flexible coiled cord" (relevant to Xircom's keyboard-port power tap, section 5). — [Operations Guide](https://archive.org/details/compaq-portable-3-operations-user-manual)
- John Elliott's Portable III page mentions the parallel socket only in passing ("the usual sockets on the back (serial, parallel and monitor)") and documents no parallel-port chip or register. — [seasip.info](https://seasip.info/VintagePC/compaq3.html)
- Michael Brutman, on standard ports: "A standard parallel port like the kind found on the original IBM PC, XT, PCjr, and AT is capable of sending a byte of data out of the port at a time, but is only capable of reading 5 bits at a time." — [Brutman, Xircom PE3 notes](https://www.brutman.com/Dos_Networking/xircom_pe3.html)
- On non-bidirectional ports the data latch's output enable is "tied permanent low, thus the data port is always output only", and reading the data port returns the last byte written. On bidirectional ports "Bit 5 of the Control Port enables or disables the bi-directional function"; "Other ports may require setting bit 6". The author advises: "test it with a logic probe or multimeter first to make sure it is in bi-directional mode." — [Beyond Logic, Interfacing the Standard Parallel Port (mirror)](https://wearcam.org/seatsale/programs/www.beyondlogic.org/spp/parallel.htm)
- IBM PS/2 machines have bidirectional ports "but use a non-standard port address to flip the direction of the port. The Xircom drivers do not recognize this and thus they have to be run in nibble mode." — [Brutman, mTCP Performance Notes](http://brutmanlabs.org/mTCP/mTCP_Performance.html)
- Forcing 8-bit input on an output-only port by overdriving the latch is possible but risky: "(or a input only port, once you blow up the latches output!)"; it needs "30 to 40mA" of sink current. — [Beyond Logic (mirror)](https://wearcam.org/seatsale/programs/www.beyondlogic.org/spp/parallel.htm)
- A safer 8-bit input trick on SPP ports: the four control lines are open-collector on classic ports, so after writing xxxx0100 to the control port they can be read as inputs; status supplies one nibble and control the other. Caveat from the same page: in ECP/EPP ports "the control port becomes totem pole outputs only". — [Beyond Logic (mirror)](https://wearcam.org/seatsale/programs/www.beyondlogic.org/spp/parallel.htm)
- Linux's PLIP documentation warns not to use the 8-bit ("Mode 1") cable on unidirectional printer ports: it causes output driver conflicts and a small risk of damage. — [Linux kernel docs, PLIP](https://docs.kernel.org/networking/plip.html)

### Inferences
- Estimate: a February-1987 AT-class Compaq most likely has an IBM-AT-style output-only port. IBM introduced the bidirectional port with the PS/2 in April 1987, after the Portable III shipped. Treat 8-bit input as unavailable until tested.
- Test to run on the real machine (DEBUG is enough; my procedure, not from a source): find the port base in the BIOS data area (`d 40:8 l 6`), write 0xFF to base, and connect a 1 kOhm resistor from one data pin (pins 2-9) to ground (pin 25). With 0x04 in base+2 (bit 5 clear) the bit must still read 1, because the output latch wins. Then write 0x24 to base+2 (bit 5 set) and read base again. If the bit now reads 0, the port is bidirectional. If it still reads 1, it is output-only. Repeat with 0x44 (bit 6). The 1 kOhm resistor keeps the current near 3-5 mA, so the test is safe on an output-only port.
- Second test: write 0x04 to base+2 (all four control lines released high) and read base+2 while pulling pin 1, 14 or 17 to ground through about 330 Ohm. If the read bit follows the pin, the control lines are open-collector and the "status + control = 8 input bits" trick is available. If the bit does not change, they are totem-pole outputs; remove the resistor promptly.
- Every recommended option below (pocket Ethernet adapter in NON mode, LapLink-cable nibble links, Crynwr PLIP) works on an output-only port, so the answer changes speed (about 2x on receive), not feasibility.

### Gaps
- No Compaq Portable III Technical Reference Guide or Maintenance and Service Guide text for the parallel port was found online. minuszerodegrees.net hosts a Portable III product bulletin and a Portable 386 service guide; neither was confirmed to cover the port's direction control.
- Port base address (0x378 or 0x3BC) and whether IRQ 7 is wired and working: not documented in any source found. Crynwr PLIP and the Xircom driver's interrupt mode need the IRQ.
- Whether Compaq used a discrete 74LS374 latch or an ASIC here: not found.

## 2. Throughput of classic parallel links on 286-class machines (nibble mode, PLIP, 8-bit modes)

### Takeaway
No measured figure for a 12 MHz 286 was found for LapLink, INTERLNK or PLIP. The best measured data for 5-bit status-line input on slow machines is Brutman's Xircom table: 22.8 KB/s on a 4.77 MHz 8088, 53.1 KB/s on an 8 MHz 8086 and 104 KB/s on a 33 MHz 386, all with full TCP/IP on top. General PLIP literature says 5 to 50 KB/s.

### Cited Findings
Nibble (4-bit, status-line input) links:
- The LapLink / "null printer" cable crosses data bits D0-D4 to the peer's status inputs: pins 2-15, 3-13, 4-12, 5-10, 6-11, plus 25-25 ground. — [Crynwr plip.doc in crynwr_mirror](https://github.com/fragglet/crynwr_mirror/blob/HEAD/binaries/plip.doc); same table in [Linux kernel docs, PLIP](https://docs.kernel.org/networking/plip.html)
- PLIP "mode 0" moves 4 bits at a time over that cable; "mode 1" needs bidirectional ports and moves a byte at a time. — [Linux kernel docs, PLIP](https://docs.kernel.org/networking/plip.html)
- Linux Network Administrator's Guide: PLIP achieves "10 kilobytes per second to 20 kilobytes per second". — [NAG2, The PLIP Driver](https://www.linuxdoc.org/LDP/nag2/x-087-2-hardware.drivers.plip.html)
- PLIP mini-HOWTO: speed "may be from 5 Kb/sec up to even 40 Kb/sec", depending on CPU, port and load. — [PLIP mini-HOWTO (mirror)](https://www.iitk.ac.in/LDP/HOWTO/text/PLIP)
- 1999 linux-parport list: users measured "about 47KB/sec" and "50KB=400Kbps" over PLIP; a reply estimates nibble mode "can push 50k/s", EPP 500 KB/s to 2 MB/s. Machines were late-1990s PCs, not 286s. — [linux-parport archive 1604](https://cyberelk.net/tim/parport/archive/current/1604.html), [1605](https://cyberelk.net/tim/parport/archive/current/1605.html)
- NetBSD plip(4): PLIP "is CPU-intensive", made worse by sending nibbles. — [NetBSD plip(4)](https://man.netbsd.org/plip.4)
- INTERLNK/INTERSVR, whole-disk copy from a Commodore PC20-II with a 20 MB MFM drive: parallel bidirectional/ECP 25 minutes, parallel normal 27 minutes, serial 115200 baud 31 minutes. Bytes copied not stated. Another poster: "parallel's nearly twice as fast, 0.7Mbps vs. 0.4 Mbps", no test conditions. — [VCFed thread](https://forum.vcfed.org/index.php?threads/laplink-cable-with-ms-dos-interlnk-intersvr.71432/)
- FastLynx with a 4-bit parallel cable: a Vogons user "thinks" it maxed out at "about 40-50 kbytes/sec" (a recollection, machine unspecified; seen via search snapshot, page not fetched). — [Vogons thread 35730](https://www.vogons.org/viewtopic.php?t=35730)
- A parallel Zip emulator driven by PALMZIP on a Book 8088 (V20, 8/10 MHz): write about 7.2 KB/s, read "around 6.3KB/sec in nibble mode"; the author concludes throughput "was likely capped by the slow speed of the processor". — [ToughDev LPT100 part 2](https://www.toughdev.com/content/2026/03/pic32mz-iomega-zip100-parallel-port-emulator-part-2-hardware-design/)

Measured 4-bit versus 8-bit input on slow CPUs (Xircom PE3-10BT, mTCP SpdTest, raw TCP with checksums, no disk):

| Machine | Port | Send KB/s | Receive KB/s |
|---|---|---|---|
| IBM 5140 Convertible, 8088 4.77 MHz | standard, no IRQ | 42.9 | 22.8 |
| IBM PCjr, V20 4.77 MHz | bidirectional, IRQ | 42.9 | 40.5 |
| IBM PS/2 Model 25, 8086 8 MHz | standard (nibble), IRQ | 87.5 | 53.1 |
| Clone 386DX-33 (reported by Trixter) | standard, no IRQ | 189 | 104 |
| Compaq 4/33i, 486DX2-66 | not stated, IRQ 7 | 208.5 | 202.7 |

— [Brutman, mTCP Performance Notes](http://brutmanlabs.org/mTCP/mTCP_Performance.html) (last updated 2023-03-31)
- Brutman's reading of that table: on a standard port the adapter "will receive data at half the send rate because it can only use the five parallel port control lines for reading". — [mTCP Performance Notes](http://brutmanlabs.org/mTCP/mTCP_Performance.html)
- D-Link DE-600/DE-620 under Linux (1994, machine unspecified): ftp transmit "> 80k bytes/sec", receive about 60-80% of transmit. — [Linux DLINK.txt](https://mjmwired.net/kernel/Documentation/networking/DLINK.txt)
- D-Link's DE-620 manual: bidirectional mode gives "about 10%" more speed than unidirectional; EPP "up to 4 times". — [D-Link DE-620 manual, archive.org](https://archive.org/download/manualsonline-id-adf6b96a-7f54-4971-8de9-afc621f74baa/adf6b96a-7f54-4971-8de9-afc621f74baa.pdf)

### Inferences
- Estimate for a 12 MHz 286 on an output-only port, interpolating between the 8 MHz 8086 (87.5 / 53.1) and the 33 MHz 386 (189 / 104): a Xircom PE3 should give roughly 60-90 KB/s receive and 100-150 KB/s send with mTCP. Receive is the direction that matters for Pi-to-Compaq video.
- Estimate: a purpose-written nibble receiver (no TCP/IP, no packet driver, unrolled polling loop) on the 286 should reach 40-100 KB/s Pi-to-Compaq if the Pi end can clock nibbles without waiting on a slow handshake. The earlier document's "30-80 KB/s" is consistent with this.
- Estimate: stock Crynwr PLIP on a 286-12 lands at 10-25 KB/s. Each nibble is individually acknowledged, and the published 40-50 KB/s figures are from machines several times faster.
- If the port turns out to be bidirectional, expect receive to roughly match send (PCjr row: 40.5 vs 22.8 KB/s at the same CPU speed).
- The VCFed INTERLNK timings are disk-bound and say little about the link's ceiling.

### Gaps
- No measured LapLink, INTERLNK, FastLynx or PLIP throughput on any 286 was found.
- No mTCP/Xircom result for a 286 is in Brutman's table (the IBM AT 5170 is listed as "known to work" but has no speed row).
- No published LapLink vendor figure (bytes per second for the parallel cable) was found in a citable source.

## 3. How can a Raspberry Pi act as the peer on a PC parallel port?

### Takeaway
Two Pi boards give Linux a real `parport` device behind proper 5 V buffering: the open-hardware pi-parport HAT (SN74LVC161284, build it yourself) and the Elesar S&P HAT (sold assembled, GBP 38.40). Joined to the Compaq with a LapLink cable, either makes the Pi a PC-style peer. Nobody has documented PLIP or a LapLink-style transfer over them, the driver has no interrupt support, and Raspberry Pi kernels ship neither `parport` nor `plip`, so Linux PLIP on the Pi is plausible but unproven and needs out-of-tree module builds.

### Cited Findings
pi-parport (worlickwerx/pi-parport; `github.com/worlickwerx/rpi-parport` returns 404):
- A Raspberry Pi HAT providing a PC-style parallel port; kernel modules `parport`, `parport_gpio`, `lp`, `ppdev`; device-tree overlay `parport-gpio`. GPL-2.0-or-later software, CERN-OHL-1.2 hardware. — [pi-parport README](https://github.com/worlickwerx/pi-parport)
- v2 and later use one SN74LVC161284; v1 used three 74AHCT541 buffers to "convert to/from the Pi's 3V3 line level and the parallel port's 5V", worked "only with a very short cable" and had no bidirectional data. v4 is shared on OSHPark with a BOM; no assembled boards are sold. — [pi-parport hardware README](https://github.com/worlickwerx/pi-parport/blob/HEAD/hardware/README.md)
- Limits stated in the README: "On a Pi 3, user space code can toggle a parallel port line at about 250 kHz"; "Bidirectional control pins are not currently supported, but bidirectional data pins are supported"; software must use ppdev or `struct parport`, not x86 port addresses. — [pi-parport README](https://github.com/worlickwerx/pi-parport)
- The driver registers the port with `PARPORT_IRQ_NONE` and `PARPORT_MODE_PCSPP`; `enable_irq`/`disable_irq` are stubs. Issue #2 "implement IRQ on low to high nACK transition" is still open (last comment 2024-08-29). — [parport_gpio.c](https://github.com/worlickwerx/pi-parport/blob/HEAD/driver/parport_gpio.c), [issue #2](https://github.com/worlickwerx/pi-parport/issues/2)
- The repo bundles generic parport code (share, ieee1284, probe, procfs, daisy, lp, ppdev) because "the Raspberry Pi Foundation does not ship the compiled modules". It does not bundle `plip`. The README's build example is kernel 4.19.75. Last push 2024-10-22; 78 stars; 17 open issues. A GitHub issue search for "plip" in the repo returns nothing. — [pi-parport](https://github.com/worlickwerx/pi-parport)

Elesar S&P HAT:
- "Raspberry Pi serial and parallel port HAT" (EA-981-8): GBP 38.40 inc VAT (GBP 32.00 ex VAT), 5 in stock when fetched 2026-10-13; "an IEEE1284 compatible parallel port" plus RS-232; supports "Raspberry Pi 5 and earlier models with a 40 pin expansion header". — [Elesar shop](https://shop.elesar.co.uk/index.php?route=product/product&product_id=76)
- Its Linux driver `parport_sphat` provides a standard parport and `/dev/lp0`; precompiled modules come from a script in the HAT EEPROM for kernels Elesar supports, otherwise you rebuild: "By default, parallel port support is not enabled on the Raspberry Pi." Repo last pushed 2026-06-11. — [elesar-uk/parport-sphat](https://github.com/elesar-uk/parport-sphat)

Transceiver and levels:
- SN74LVC161284: 19-bit IEEE 1284 bus interface (eight bidirectional bits, five cable-side drivers, four receivers); logic VCC 3-3.6 V; VCC CABLE 3-3.6 V or 4.7-5.5 V; cable-side pins are 5 V tolerant; HD pin selects totem-pole or open-drain outputs; integrated 1.4 kOhm pull-ups on the cable side; status ACTIVE. — [TI SN74LVC161284](https://www.ti.com/product/SN74LVC161284)
- PC parallel port outputs are "normally TTL logic levels"; ports differ in drive (examples listed: sink/source 6-20 mA) and some cards have 1 kOhm pull-ups to 5 V. — [Beyond Logic (mirror)](https://wearcam.org/seatsale/programs/www.beyondlogic.org/spp/parallel.htm)

Linux PLIP on the Pi side:
- Raspberry Pi's kernel configs on branch rpi-6.12.y (`bcm2709_defconfig` for 32-bit Pi 2/3, `bcm2711_defconfig` for arm64) contain no PARPORT or PLIP entries. They do enable `USB_PRINTER`, `USB_SERIAL_FTDI_SIO`, `USB_SERIAL_CH341` and `USB_SERIAL_MOS7720` as modules. — [raspberrypi/linux bcm2709_defconfig](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/arch/arm/configs/bcm2709_defconfig)
- Mainline Linux still carries `drivers/net/plip/plip.c` (checked 2026-10-13). — [torvalds/linux plip](https://github.com/torvalds/linux/tree/master/drivers/net/plip)
- The Linux driver implements the Crynwr mode 0 protocol and names the Crynwr packet driver as a peer. Without an IRQ it runs in a polling mode; the peer's trigger timeout then has to be about 10^6/HZ microseconds (10000 at HZ=100), set with `plipconfig plipX trigger 10000`. Defaults: trigger 500 microseconds, nibble 3000 microseconds. The source logs "has no IRQ. Using IRQ-less mode, which is fairly inefficient!". — [Linux kernel docs, PLIP](https://docs.kernel.org/networking/plip.html), [plip.c](https://github.com/torvalds/linux/blob/master/drivers/net/plip/plip.c)
- For a DOS peer the Linux interface needs ARP turned on ("To use with DOS box, please do (Turn on ARP switch): # ifconfig plip[0-2] arp"). — [plip.c](https://github.com/torvalds/linux/blob/master/drivers/net/plip/plip.c)

DOS side (Crynwr PLIP):
- `PLIP.COM` is a class-1 (Ethernet-emulating) packet driver. Usage string: "usage: parallel [options] <packet_int_no> [-t] <hardware_irq> <io_addr> [<Ethernet_address>]"; defaults IRQ 7, I/O 0x378. The sender starts a packet by writing 08h, which raises the peer's ACK line to interrupt it. The source has no `.286` directive. Send waits up to 18 ticks and receive 10 ticks of 27.5 ms for the peer. — [plip.asm](https://github.com/fragglet/crynwr_mirror/blob/HEAD/plip.asm), [timeout.asm](https://github.com/fragglet/crynwr_mirror/blob/HEAD/timeout.asm)
- Crynwr's index lists plip.zip as a parallel-port driver with Ethernet emulation (June 1995); packetdriversdos.net lists PLIP.COM version 11.0 (1993). — [Crynwr driver index](http://crynwr.com/drivers/00index.html), [packetdriversdos.net](https://www.packetdriversdos.net/)

Non-PLIP software for a LapLink cable:
- ppcopy: DOS `ppread.com`/`ppwrite.com` (ppread is 237 bytes, typeable in DEBUG) and Linux tools, over a LapLink cable; nibble protocol with a clock bit, checksummed chunks, documented in PROTOCOL.md. The Linux binaries are i386/x64 only and "talk to the port directly". No speed figures. Updated 2026-09. — [dmeybohm/ppcopy](https://github.com/dmeybohm/ppcopy)
- ruby-interlnk: an INTERLNK client in Ruby; serial-over-TCP only, "Parallel port support" is on its TODO list. — [sarahemm/ruby-interlnk](https://github.com/sarahemm/ruby-interlnk)

### Inferences
- 5 V HAZARD: never wire the Compaq's DB-25 straight to the Pi's 40-pin header. The Compaq's data and control outputs are 5 V TTL and its inputs may be pulled up to 5 V; the Pi 3 B+ GPIO is 3.3 V and not 5 V tolerant. Everything on the Pi side must sit behind a 5 V-tolerant buffer: the SN74LVC161284 on either HAT, or for a hand-built link a 74LVC245 powered at 3.3 V for Compaq-to-Pi lines and a 74HCT245/74AHCT541 powered at 5 V for Pi-to-Compaq lines (the pi-parport v1 approach).
- Both HATs present a host-style port, the same role as the Compaq's. The join is therefore a LapLink (null-printer) cable, which is exactly what PLIP mode 0 expects. No "peripheral mode" is needed.
- Linux PLIP over `parport_gpio` should be possible in principle: `plip` only needs generic parport operations, and the IRQ-less mode exists for ports with no interrupt. The Crynwr side waits roughly 0.27-0.5 s for its peer, far longer than the Pi's 10 ms poll, so no DOS-side timeout change should be needed. The 500 microsecond trigger wait on the Linux side may be too short for a 286 servicing an interrupt under DOS; raising it with `plipconfig` is the documented fix. All of this is untested by anyone I could find.
- Work required for PLIP on the Pi: build `parport`, `parport_gpio` (or `parport_sphat`) and `plip.ko` out of tree against the running Raspberry Pi kernel headers, and repeat after kernel updates. pi-parport's documented build is from the 4.19 era; expect patching for 6.12.
- A custom user-space nibble sender on the Pi (direct GPIO register writes through a HAT's buffer, or ppdev at about 250 kHz per line toggle) paired with a small DOS receiver is the simpler and faster route for streaming frames. It avoids PLIP's per-nibble acknowledge and all kernel work. Estimate 40-100 KB/s to the 286; ppdev's 250 kHz toggle rate would cap an unoptimised sender near 30-60 KB/s.
- A Pi Zero W can carry either HAT (same 40-pin header) and forward over Wi-Fi, but it adds nothing the 3 B+ cannot do directly.
- Parts estimate (not sourced, my estimate): pi-parport bare boards from OSHPark plus SN74LVC161284 (48-pin SSOP, fine-pitch soldering) and passives about $25-40 for a set; LapLink cable $10-20; 74LVC245/74HCT245 hand-built buffer board under $10.

### Gaps
- No report of PLIP, LapLink, INTERLNK or ppcopy running over pi-parport or the Elesar HAT was found.
- Whether pi-parport's modules build on the kernel in Raspberry Pi OS based on Debian 13 was not verified. Which kernel branch that OS ships, and whether the 32-bit OS on a 3 B+ boots the armv7 or the 64-bit kernel, were not verified either.
- Whether `plipconfig` is still packaged in Debian 13's net-tools: not checked.
- The Elesar HAT's buffer chip, data-direction support and interrupt support are not stated on its product page.
- No SN74LVC161284 unit price was retrieved from TI or a distributor.
- CONFIG_HZ for the Pi kernel: not set explicitly in the defconfig; the value in use was not confirmed.

## 4. USB options: printer cables, FTDI, CH341A, and microcontroller bridges

### Takeaway
Ordinary USB-to-parallel printer cables cannot do bit-level I/O and are the wrong end of the link anyway. An FT232H breakout (3.3 V drive, 5 V-tolerant inputs, about $15) or a Pico-class microcontroller behind level shifters can act as a nibble-mode peer, but no existing project presents a LapLink or Crynwr-PLIP port to a PC: every "plipbox"-style bridge found is Amiga-only, so the firmware and the DOS program would both be new work.

### Cited Findings
USB printer cables:
- "Many USB parallel port devices appear to Linux as a USB printer, bypassing the parport driver stack." — [pi-parport README](https://github.com/worlickwerx/pi-parport)
- The one mainline exception is the Lucent USS-720 chip: in automatic mode "Only printers may be connected"; in manual mode the `uss720` driver exposes a parport, but "some operations are three orders of magnitude slower than on a PCI/ISA Parallel Port, so timing critical applications might not work." The driver depends on PARPORT. — [Linux drivers/usb/misc/Kconfig](https://github.com/torvalds/linux/blob/master/drivers/usb/misc/Kconfig)
- Raspberry Pi kernels (rpi-6.12.y) do not enable PARPORT, so `uss720` and the MCS7715 parport function are not built; only the USB printer class driver is. — [bcm2709_defconfig](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/arch/arm/configs/bcm2709_defconfig)

FTDI:
- FT232H: 3.3 V I/O "with built-in tolerance for 5V"; asynchronous 245 FIFO up to 8 MB/s; synchronous 245 FIFO up to 40 MB/s; bit-bang mode available (figures from FTDI datasheet text via search snapshots; ftdichip.com returned 403 to direct fetch). — [FTDI FT232H product page](https://ftdichip.com/?p=332)
- FT245R: "data transfer rates up to 1Mbyte / second" with D2XX drivers (300 KB/s through the virtual COM port); VCCIO 1.8-5 V; "True 5V/3.3V/2.8V/1.8V CMOS drive output and TTL input". — [FT245R datasheet (mirror)](https://pdf.direnc.net/upload/ft245r-datasheet.pdf), [FTDI UM245R](https://ftdichip.com/products/um245r/)
- Adafruit FT232H breakout: $14.95, USB-C, shown out of stock when fetched 2026-10-13. — [Adafruit product 2264](https://www.adafruit.com/product/2264)

CH341A:
- The CH341's parallel function is an 8-bit EPP or MEM interface where the chip generates the strobes (AS#, DS#, WR#; or A0, RD#, WR#). GPIO use needs out-of-tree drivers; one measured about 2.2 kHz pin toggling from a shell script, and its bit-banged SPI costs about 6.5 ms of USB overhead per byte. — [CNX Software on the CH341 GPIO driver](https://www.cnx-software.com/2018/02/16/wch-ch341-usb-to-serial-chip-gets-linux-driver-to-control-gpios-over-usb/), [gschorcht/i2c-ch341-usb](https://github.com/gschorcht/i2c-ch341-usb), [spi-ch341-usb README](https://github.com/R2D2lab/spi-ch341-usb)

Microcontroller bridges that exist:
- plipbox: "an Arduino-based device that allows to connect low-end classic Amigas via Ethernet to your local network"; grew out of plip2slip, which used the Amiga MagPLIP protocol; ships Amiga drivers only. Still maintained (updated 2026-10-09). — [cnvogelg/plipbox](https://github.com/cnvogelg/plipbox)
- Other plipbox descendants are also Amiga-only: plipUltimate ("Network interface & SD card reader for Classic Amigas"), ESP32fi ("A parallel port ESP32 plipbox for the Amiga. ... Do not build. Not tested"), PLIPBOX_Pico (no README, 4 stars, 2024). — [tehKaiN/plipUltimate](https://github.com/tehKaiN/plipUltimate), [wiretap-retro/ESP32fi](https://github.com/wiretap-retro/ESP32fi), [jockel71/PLIPBOX_Pico](https://github.com/jockel71/PLIPBOX_Pico)
- ESP32 parallel projects found are printer emulators that capture what a PC prints: ESP32_VirtualPrinter (forwards to a TCP socket, "very rough") and ParallESP (prints captured data over serial; Wi-Fi is a goal). Neither has a DOS driver or a device-to-PC data path. — [rsp-git/ESP32_VirtualPrinter](https://github.com/rsp-git/ESP32_VirtualPrinter), [Ilikemining1/ParallESP](https://github.com/Ilikemining1/ParallESP)
- LPT100: a PIC32MZ board that emulates an Iomega parallel Zip drive from USB disk images; works with PALMZIP on a Book 8088 at about 7.2 KB/s write and 6.3 KB/s read (nibble mode). The author chose the PIC32MZ for its "5V tolerant pins". PALMZIP's bidirectional mode showed an empty directory and a Pocket 386 failed to read. — [ToughDev LPT100 part 2](https://www.toughdev.com/content/2026/03/pic32mz-iomega-zip100-parallel-port-emulator-part-2-hardware-design/), [Hackaday, 2026-03-17](https://hackaday.com/2026/03/17/zip-drive-emulator-puts-big-disks-back-on-lpt/)
- RP2350 (Pico 2) GPIOs marked FT accept up to 5.5 V only while IOVDD is present at 3.3 V; outputs stay 3.3 V; ADC-capable pins are excluded (forum posts quoting the datasheet). — [cctalk thread on RP2350 5 V tolerance](https://classiccmp.org/mailman3/hyperkitty/list/cctalk@classiccmp.org/thread/DKAPPVXR5UDDK23MBFRIWFB7CUIVMMBX/)

### Inferences
- A USB printer cable is unusable for two independent reasons: the Pi's kernel treats it as a printer-class device with no pin-level access, and both it and the Compaq are host-role ends (the cable expects to plug into a printer).
- FT232H as a nibble peer (estimate): wire five FT232H outputs to the Compaq's five status inputs and three or four FT232H inputs to Compaq data pins 2-5. 3.3 V highs satisfy TTL input thresholds, and the Compaq's 5 V outputs are within the FT232H's stated tolerance, so no level shifter is needed. Check with a meter that the Compaq's status inputs are not pulled above 5 V and add 1 kOhm series resistors as cheap insurance. In asynchronous bit-bang mode the Pi clocks out nibble-plus-strobe bytes at a fixed rate and the 286 polls the strobe bit; estimate 40-100 KB/s Pi-to-Compaq with no per-nibble acknowledgement. If each nibble waits for an acknowledgement over USB, throughput collapses to roughly 1 KB/s because every USB round trip costs about a millisecond.
- The FT245R/FT232H "245 FIFO" interface (RD#, WR, RXF#, TXE# with an 8-bit bus) maps well onto a PC parallel port only when the port is bidirectional. On an output-only port it gives a fast Compaq-to-Pi path but no 8-bit Pi-to-Compaq path, which is the direction video needs.
- CH341A is not suitable: its fast modes make it a bus master, and its GPIO path is thousands of times too slow.
- Pico bridge (estimate): an RP2040 Pico with PIO can run the nibble handshake at any speed the 286 can manage and present USB CDC to the Pi (USB full speed, about 1 MB/s) or Wi-Fi on a Pico W. 5 V HAZARD: treat original Pico (RP2040) GPIO as 3.3 V-only and put a 74LVC245 between the Compaq's outputs and the Pico. A Pico 2 (RP2350) tolerates 5 V on its FT pins only while powered, and the Compaq can be on while the Pico is off, so use the buffer there too. Pi Pico about $4-7, buffer chips under $2, DB-25 male breakout about $5-10 (my estimates, not sourced). Firmware and the DOS receiver are both new code; the Pico's advantage over direct Pi GPIO is exact timing and electrical isolation from the Pi, not higher throughput.
- A Teensy or Arduino adds nothing over a Pico here; a 5 V AVR Arduino avoids level shifting on the Compaq side but its USB serial is slow (estimate).
- The quickest route to a standard stack through a microcontroller would be to implement the Crynwr mode 0 protocol in firmware and bridge it to USB networking, giving the Compaq a packet driver (`PLIP.COM`) with no DOS-side development. Nobody appears to have published this.

### Gaps
- No Pico, ESP32, Teensy or Arduino project that speaks LapLink, INTERLNK or Crynwr PLIP to a PC was found. GitHub repository searches for "plip pico", "plip esp32", "laplink pico", "pico lpt dos", "lpt wifi dos", "dos lpt esp32", "parallel port packet driver", "lpt ethernet dos packet driver" and "lpt ne2000" returned only the Amiga projects above. Three web searches for a modern parallel-port Wi-Fi or Ethernet adapter with a DOS packet driver (Hackaday, Tindie, Vogons, VCFed) also returned nothing relevant.
- No Tindie or other retail listing for a parallel-port network bridge for DOS PCs was found.
- RP2040 (original Pico) voltage tolerance was not checked against the datasheet in this pass.
- FT232H asynchronous bit-bang maximum rate and latency-timer behaviour were not retrieved from FTDI's own documents (site blocked fetches).

## 5. Pocket parallel-port Ethernet adapters (Xircom PE3, D-Link DE-600/DE-620, Accton EtherPocket)

### Takeaway
The Xircom PE3-10BT is the proven choice: its packet driver runs on output-only ports with a `NON` switch, works from DOS 2.1 up, has been used on an IBM AT, and measured 53 KB/s receive on an 8 MHz 8086. It needs its own power (12 V DC adapter, since the Compaq has no PS/2 keyboard port) and 2026 asking prices run about $95 to $380.

### Cited Findings
Xircom PE3:
- Three models, identical to software: PE3-10B2 (coax), PE3-10BT (RJ-45 10BASE-T), PE3-10BC (both). Each has an Ethernet chipset and a 32 KB buffer; 10 Mb/s only. — [Brutman, Xircom PE3 notes](https://www.brutman.com/Dos_Networking/xircom_pe3.html)
- Bundled software includes a DOS packet driver, `PE3PD.COM`. Switches: `NON` ("Force the driver to treat the parallel port as standard (non-bidirectional)"), `SINT=` 60-80, `LPT=` 1-3, `INT=` 0 or 3-15 ("If you use zero the adapter works in a polling mode"), `IOADDRESS=` 240-380, `LINKDISABLE`, `NOEPP`. Example: `pe3pd SINT=62 LPT=2 INT=5 NON`. — [Brutman, Xircom PE3 notes](https://www.brutman.com/Dos_Networking/xircom_pe3.html)
- "The Xircom can support any parallel port ... Standard ports work, but they are half as slow when receiving data as compared to sending data." — [Brutman, Xircom PE3 notes](https://www.brutman.com/Dos_Networking/xircom_pe3.html)
- Tested by Brutman: IBM PCjr, PC 5150, XT 5160, 5140 Convertible, "IBM PC AT 5170", PS/2 Model 25, PS/2 L40SX, a 386-40 with standard port; reported by others: Data General One Model/2 and "Commodore C286-LT portable". One failure: Olivetti Prodest PC-1 (non-standard port). — [Brutman, Xircom PE3 notes](https://www.brutman.com/Dos_Networking/xircom_pe3.html)
- DOS version: "The Xircom manual does not specify a required version of DOS ... I have used everything from DOS 2.1 upwards." — [Brutman, Xircom PE3 notes](https://www.brutman.com/Dos_Networking/xircom_pe3.html)
- Power: "The parallel port does not provide enough power to operate the device". Two options: a wall transformer "that provided 12VDC output", or a "Phantom AC Power Cable" taking power from a PS/2 keyboard port. — [Brutman, Xircom PE3 notes](https://www.brutman.com/Dos_Networking/xircom_pe3.html)
- No printer pass-through; plug it directly into the port; "Do not connect the Xircom to a parallel port while the computer is turned on." — [Brutman, Xircom PE3 notes](https://www.brutman.com/Dos_Networking/xircom_pe3.html)
- Drivers: Brutman hosts `xircom_pe3_10bt_353.exe` (md5 29c9303fb47cc7e85599b06d98f8ec8b) because Intel no longer does; retrocmp.de hosts driver version 3.53 (`pe3-v353.zip`) and the user's guide PDF, and its author runs the adapter "in non-bidirectional mode (NON)" on PC/XT machines with mTCP. — [Brutman, Xircom PE3 notes](https://www.brutman.com/Dos_Networking/xircom_pe3.html), [retrocmp.de](https://retrocmp.de/transfer/xircom-pe3.htm)
- Measured throughput: see the table in section 2. — [Brutman, mTCP Performance Notes](http://brutmanlabs.org/mTCP/mTCP_Performance.html)
- 2026 eBay asking prices seen in a search snapshot (listing dates not shown, not sold prices): used PE3-10BT $95 + $10 shipping; new/open-box $134.99; $209.99 and $210; a product page at $273.62; Radwell $318.71 and $382. Accessories: used Xircom AC power adapter $39; manual plus driver diskette $45. — [eBay item 232482077642](https://www.ebay.com/itm/232482077642), [eBay product 1004526180](https://www.ebay.com/p/1004526180), [eBay UK item 334558601757](https://www.ebay.co.uk/itm/334558601757), [eBay power adapter 384998749879](https://www.ebay.com/itm/384998749879), [eBay manual and diskette 145791138841](https://www.ebay.com/itm/145791138841)
- A Swiss reseller lists the coax-only PE3-10B2 at 40 CHF, zero in stock. — [revampit.ch](https://revampit.ch/index.php/en/shop-en/manufacturer/xircom)

D-Link DE-600 and DE-620:
- Crynwr `DE600.COM` (version 11.1, 1993): "usage: de600 [options] packet_int_no", "requires no additional parameters". Its source begins with `.286c`, so it is assembled with 286 instructions. — [Crynwr install.doc](https://github.com/fragglet/crynwr_mirror/blob/HEAD/binaries/install.doc), [de600.asm](https://github.com/fragglet/crynwr_mirror/blob/HEAD/de600.asm)
- `DE620PD.COM` v1.28 (D-Link, 1996) and SETUP620.EXE are downloadable as `de620ct.exe`; drivers and manual for the DE-620CT are also on archive.org. — [packetdriversdos.net](https://www.packetdriversdos.net/), [archive.org DE620CT](https://archive.org/details/DE620CT)
- D-Link's manual: unidirectional is the original Centronics mode and is "slightly slower than Bi-directional"; bidirectional gains "about 10%"; EPP "up to 4 times"; "not all ports are completely compatible with the DE-620 so if you can't get it to work please revert to Uni-directional mode". — [D-Link DE-620 manual, archive.org](https://archive.org/download/manualsonline-id-adf6b96a-7f54-4971-8de9-afc621f74baa/adf6b96a-7f54-4971-8de9-afc621f74baa.pdf)
- Under Linux in 1994: ftp transmit "> 80k bytes/sec", receive 60-80% of that. — [Linux DLINK.txt](https://mjmwired.net/kernel/Documentation/networking/DLINK.txt)

Accton EtherPocket:
- `PEPKTDRV.COM`, "ACCTON EtherPocket v2.0 (930610)", is downloadable. — [packetdriversdos.net](https://www.packetdriversdos.net/) (link target: georgpotthast.de/sioux/pktdrv/pepktdrv.zip)

### Inferences
- The PE3-10BT is compatible with every stated constraint: output-only port (`NON`), 286, DOS 3.1 (driver proven on DOS 2.1 and up), and a Pi 3 B+ Ethernet port on the other end. Use `INT=0` (polling) first, since the Compaq's parallel IRQ is unverified.
- Power: the Portable III keyboard uses a coiled cord, not a PS/2 mini-DIN, so plan on the 12 V DC wall adapter. Confirm the barrel polarity and that an adapter is in the listing; a bare unit may arrive with only the PS/2 phantom cable.
- Estimated throughput on the 286-12 with an output-only port: 60-90 KB/s receive, 100-150 KB/s send (section 2). That is 5-8 times the 11.5 KB/s serial ceiling.
- The DE-600's `.286c` driver suits this machine (it would not run on an 8088). The DE-600 is 10BASE2 coax in most versions (my recollection, not sourced), which a Pi cannot use without a media converter; prefer the DE-620CT (the "T" indicates twisted pair, per the product name) or the PE3-10BT/10BC.
- Both ends then speak ordinary TCP/IP: mTCP on DOS, standard Linux networking on the Pi. No kernel modules, no level shifting and no 5 V exposure for the Pi, because the Pi only sees Ethernet.
- Budget (estimate): $100-250 for a PE3-10BT with power adapter in 2026, more if the adapter must be bought separately ($39 seen).

### Gaps
- eBay sold-listing prices could not be retrieved (HTTP 403); the figures above are asking prices of unknown date.
- No 2026 price or availability was found for the D-Link DE-600/DE-620 or Accton EtherPocket (one DE-620CT retailer page returned 403).
- No measured DOS throughput was found for the DE-600, DE-620 or EtherPocket on any 8088/286.
- Whether the Accton driver supports output-only ports and 286s: not found.
- The PE3's 12 V current draw and connector polarity: not found in the sources read (the user's guide PDF on retrocmp.de was not opened).
- mTCP's minimum DOS version and resident memory of `PE3PD.COM` were not checked in this pass.
- The Vogons thread on PE3 throughput (viewtopic p=1439256) and the thread "Parallel-to-ethernet for LAN/internet access" (t=81275) could not be fetched.

## 6. What else the parallel port enables: storage and sound devices, and whether the Pi can feed them

### Takeaway
Parallel storage is the useful extra: a Zip drive with PALMZIP, or an SD-card adapter with a DOS driver, gives the Compaq tens to hundreds of megabytes for big programs, though at single-digit to low-double-digit KB/s on an output-only port. Sound devices work on output-only ports but are driven by the 286 itself, so the Pi cannot feed them, and everything competes for the single port.

### Cited Findings
Storage:
- Iomega's official parallel Zip driver "requires at least a 286"; PALMZIP exists to support Zip drives on 8088s. — [ToughDev LPT100 part 2](https://www.toughdev.com/content/2026/03/pic32mz-iomega-zip100-parallel-port-emulator-part-2-hardware-design/)
- The parallel Zip protocol has four modes: nibble (standard port), bidirectional, EPP, ECP. — [ToughDev LPT100 part 1](https://www.toughdev.com/content/2026/02/pic32mz-iomega-zip100-parallel-port-emulator-part-1-dosbox-qemu-testing/)
- PALMZIP in nibble mode on a Book 8088: about 7.2 KB/s write, 6.3 KB/s read (against the LPT100 emulator, which the author says is close to a real drive). — [ToughDev LPT100 part 2](https://www.toughdev.com/content/2026/03/pic32mz-iomega-zip100-parallel-port-emulator-part-2-hardware-design/)
- LPT100 is a Zip-drive emulator serving disk images up to 1 GB from USB storage, a "GoTek floppy emulator for LPT Zip drives". — [Hackaday, 2026-03-17](https://hackaday.com/2026/03/17/zip-drive-emulator-puts-big-disks-back-on-lpt/)
- A Vogons test on a Tandy 1000 RL (8086, unidirectional port) found only PALMZIP worked, and that not every Zip 100 drive is PALMZIP-compatible (search snapshot; page not fetched). — [Vogons post 1411444](https://www.vogons.org/viewtopic.php?p=1411444)
- sdpp: an SD card on the parallel port with an MS-DOS block driver. Wiring is bit-banged SPI: D0 MOSI, D1 clock, D2 chip select, SELECT (pin 13) MISO, so it needs only an output-only port. The breakout must have level shifters. Powering the card from data pins is optional and "potentially dangerous" on pre-IEEE-1284 ports. The driver is built with Borland C++ 3.1. — [nilseuropa/sdpp](https://github.com/nilseuropa/sdpp)
- Micro Solutions Backpack: one manual lists "100% IBM compatible parallel printer port", 128K memory and "DOS version 3.1 or above"; the drive is EPP-aware but does not require EPP; DOS CD-ROM driver is `BPCDDRV.SYS`. — [Backpack manual, retrocmp.de](https://www.retrocmp.de/hardware/backpack/617550en.pdf)

Sound:
- OPL2LPT V2: an OPL2 (AdLib) card for the parallel port, EUR 53.24, shown sold out with the OPL3LPT suggested instead. The `ADLIPT` TSR is "for 386+ machines"; the `ADPATCH` game patcher is for "any processor, also 8086,80286". Uses data lines D0-D7 plus control lines. — [Serdashop OPL2LPT](https://www.serdashop.com/OPL2LPT)
- CVX4: a Covox Speech Thing clone, EUR 18.15 (regular EUR 22.99), stock status ambiguous on the page. — [Serdashop CVX4](https://www.serdashop.com/CVX4)

### Inferences
- A parallel Zip drive (or the LPT100 emulator) with PALMZIP is the proven route to 100 MB of storage on a slotless 286 with an output-only port. Estimate 10-25 KB/s on the 286-12, scaling the 8088 figure by CPU speed; that is slow for loading a multi-megabyte game but removes the floppy-size limit. Iomega's own driver may also run, since it needs a 286.
- A Pi cannot usefully "be" the Zip drive without building something like LPT100; no Pi or Pico Zip emulator was found. If the goal is a Pi-served drive letter, mTCP NetDrive over a pocket Ethernet adapter achieves it with no new hardware design and at higher speed.
- Covox-type DACs and the OPL2LPT are written to by the 286 one sample or register at a time. The Pi cannot feed them directly; audio data would first have to reach the Compaq over another link, and the Compaq has only one parallel port. Keeping sound on the Pi's own output, as the earlier document recommends, stays the right call.
- Port contention is the real constraint: the Xircom has no pass-through, so adapter, Zip drive and sound device are mutually exclusive unless swapped by hand with the power off.
- An Ethernet adapter subsumes most of these: NetDrive for storage, streaming for graphics, and the serial port stays free for Kermit.

### Cross-option comparison (all sections; throughput figures for the 286-12 are estimates unless marked measured)

| Option | Compaq-side software | Pi-side software | Est. Pi-to-Compaq speed | Buy (2026) | Main risks |
|---|---|---|---|---|---|
| Xircom PE3-10BT + mTCP | `PE3PD.COM NON INT=0`, mTCP | none beyond normal networking | 60-90 KB/s (measured 53 on 8086-8, 104 on 386-33) | $95-380 asking, plus 12 V adapter ($39 seen) | price; needs external power; occupies the port |
| D-Link DE-620CT | `DE620PD.COM` | none | similar class; no DOS measurement | price not found | unidirectional mode supported but unmeasured |
| Elesar S&P HAT or pi-parport + LapLink cable, custom nibble protocol | new DOS receiver (ppcopy shows a 237-byte one is possible) | user-space sender via ppdev or GPIO | 40-100 KB/s | GBP 38.40 HAT (or DIY board) + cable $10-20 | all software is new; kernel module build for ppdev; untested path |
| Same hardware, Crynwr PLIP to Linux `plip` | `PLIP.COM 0x60 7 0x378`, mTCP | out-of-tree `parport`, driver, `plip` modules, IRQ-less mode | 10-25 KB/s | same | never documented on a Pi; needs Compaq IRQ 7; kernel maintenance |
| FT232H breakout wired to DB-25 | new DOS receiver | libftdi bit-bang sender | 40-100 KB/s open-loop | about $15 + connector | new software both ends; verify port voltages; no flow control unless added |
| Pico (PIO) + 74LVC245 buffer, USB to Pi | new DOS receiver (or `PLIP.COM` if firmware speaks Crynwr mode 0) | serial or network over USB | 40-100 KB/s | about $15 in parts | firmware is new; 5 V buffering mandatory |
| USB-to-parallel printer cable | - | - | not possible | - | printer-class only; wrong role |
| CH341A | - | - | not practical | - | GPIO path about 2 kHz |
| Zip drive or LPT100 + PALMZIP | `PALMZIP.SYS` | none (not a Pi link) | 10-25 KB/s disk | used Zip drive price not researched | storage only; drive compatibility varies |

### Gaps
- PALMZIP's own documentation (Klaus Peichl's page) was not located in this pass; 286 throughput and bidirectional behaviour are unconfirmed.
- LPT100 availability (for sale, open-source release) was not established from the article text scanned.
- Backpack compatibility with 286/8088 CPUs and strictly output-only ports is not stated in the sources found.
- OPL3LPT price, and whether CVX4 also emulates the Disney Sound Source, were not on the pages fetched.
- No source was found on running two parallel devices through a switch box with the Xircom adapter.
- Used parallel Zip drive prices in 2026 were not researched.
