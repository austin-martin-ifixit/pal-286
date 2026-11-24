# Serial (RS-232) link between a Compaq Portable III and a Raspberry Pi: speed and capability

Researched 2026-10-13. Scope: the Compaq Portable III (80286, 1987), MS-DOS Kermit 3.16, an FTDI USB-RS232 adapter on a Raspberry Pi 3 B+, and a full-handshake null modem cable.

How to read the evidence labels:

- **Cited Findings** carry a URL. Three kinds of source are used:
  - *Read directly*: I fetched the page or file and read it.
  - *Kermit source/docs*: I downloaded the official archives from kermitproject.org and read the files. Line numbers are given. `msk316src.zip` is the 3.16 source (its version string is "MS-DOS Kermit 3.16, 31 Oct 2000"). `msk314.zip` holds the last full documentation set (KERMIT.UPD January 1995, KERMIT.BWR June 1995). The 3.16 archive ships only a change list, so documentation quotes are 3.14-era and behaviour was checked against the 3.16 source.
  - *Search excerpt*: the page blocked direct fetch (HTTP 403 or 429); the text is what the search tool quoted from it. Treat these as weaker.
- **Inferences** are my estimates or reasoning. Each is labelled.
- **Gaps** say what could not be found.

Corrections to `docs/graphics-research.md` are flagged with **Correction** inside the relevant section.

## Which UART does the Compaq Portable III have, and can it be swapped for a 16550A?

### Takeaway
No source I could reach names the Portable III's UART chip or says whether it is socketed. The machine's own software can answer the type question in a minute (Kermit's `SHOW COMMUNICATIONS`, or a scratch-register test); the socket question needs eyes on the board.

### Cited Findings
- John Elliott's Portable III page names no UART. It lists serial, parallel and monitor only as "the usual sockets on the back". It describes the motherboard as smaller and more specialised than the Portable II's, with no ISA slots and two daughterboard connectors: one for video, one for memory expansion and/or a modem. — [seasip.info, read directly](https://seasip.info/VintagePC/compaq3.html)
- The Total Hardware 99 entry for the Portable III board lists a serial port connector (CN3) and jumpers that reassign the port: E3/E4 select "COM1 Serial", "COM1 Modem", "COM2 Serial" or "COM2 Modem"; E5/E16 select IRQ4 (COM1) or IRQ3 (COM2). E7 enables or disables the printer port. Switch CN8/6 sets CPU speed, 8 MHz (on) or 12 MHz (off). Chip set: "Unidentified". No UART is named. — [stason.org TH99, read directly](https://stason.org/TULARC/pc/motherboards/C/COMPAQ-COMPUTER-CORPORATION-286-PORTABLE-III.html)
- A chip-marking inventory of one Portable III logic board lists these under "Other Socketed ICs": AMD N80L286-12/S CPU, Intel D80287-8, and Intel 106436-001 "(c) COMPAQ '87", plus ROMs 109737-002 and 109738-002. No UART, RS-232 driver or 1.8432 MHz crystal is listed. The page's inventory is incomplete. — [sharebrained.com, read directly](https://sharebrained.com/vintage/computer/compaq/portable-iii/)
- Elliott identifies part 106436-001 as the keyboard controller, "probably the same one used in the Portable II". — [seasip.info, read directly](https://seasip.info/VintagePC/compaq3.html)
- The Portable III user manual calls the built-in port a "9-Pin Asynchronous Communications" interface and lists two options, an "Asynchronous Communications/Parallel Printer Board" and a "Second Asynchronous Communications Interface Board" (page 8-12). Its OCR text contains no "8250", "16450", "16550" or "UART". — [archive.org compaqportableiiimanual, OCR text read directly](https://archive.org/details/compaqportableiiimanual)
- The February 1987 Product Bulletin lists an "Asynchronous Communications Interface" as standard and says one option (the context reads like the internal modem; the OCR is rough) "frees asynchronous communications interface for other serial devices". It names no chip. It mentions a Technical Reference, so a Portable III technical reference guide existed. — [minuszerodegrees.net, PDF text layer read directly](https://minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Product%20Bulletin%20-%20First%20Edition%20(FEB87).pdf)
- The Compaq Portable 386 Maintenance and Service Guide refers to the chip only generically in its diagnostic codes (1101-01 "UART DLAB bit failed", 1101-06 "UART THRE bit failed", 1101-08 "UART TX/RX buffer failed"). The text layer I extracted contains no "16450" or "8250". — [minuszerodegrees.net, PDF text layer read directly](https://www.minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20386%20-%20Maintenance%20and%20Service%20Guide.pdf)
- MS-DOS Kermit reports the UART type: `SHOW COMMUNICATIONS` prints "16550A UART FIFO" when a working FIFO is present. "If Kermit does not say you have a 16550A UART FIFO, and you are suffering poor performance or data loss, replace it (if possible) with a 16550A." — [KERMIT.BWR 3.14, section 11, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)
- Kermit 3.16 tests for a real 16550A by writing 87h to the FIFO control register and checking that both FIFO-enabled bits read back; otherwise it turns FIFO mode off. — [msxibm.asm lines 7270-7286, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- A 16450 can be told from an 8250 in software: write a value such as 2Ah to the scratch register; if it reads back, the chip has a scratch register (16450 or later). — [Wikibooks, Serial Programming/8250 UART Programming, search excerpt](https://en.wikibooks.org/wiki/Serial_Programming/8250_UART_Programming)
- The 16450 was the UART used in the PC AT; a 16550 runs in 16450 (no FIFO) mode by default. — [Wikipedia, 8250 UART, search excerpt](https://en.wikipedia.org/wiki/8250_UART); [VCFed thread, read directly](https://forum.vcfed.org/index.php?threads/8088-and-modem-baud-rates-16450-uart.79806/)

### Inferences
- **Estimate:** the chip is most likely a FIFO-less 16450-class part (or an 8250A/82C50-family equivalent). Basis: the machine is an AT-class design announced in February 1987, and nothing found mentions a FIFO. This is a guess from the period, not a documented fact. Design the program to work without a FIFO and to use one if it finds it.
- **Inference:** the jumper-selectable COM1/COM2 and IRQ4/IRQ3 assignment means the program should not hard-code 3F8h/IRQ4. Read the port base from the BIOS data area (0040:0000) or take it as a parameter.
- **Inference (weak):** the one board inventory found lists the CPU, 287, keyboard controller and ROMs as socketed and does not list a UART. That fits a soldered or integrated UART, but the inventory is incomplete, so it proves nothing.
- **Correction:** `graphics-research.md` says "The Portable 386 has a 16450". I could not confirm it. The Portable 386 service guide text I could read never names the part.
- **Estimate:** a 16550A only drops in if the existing part is a discrete DIP-40 8250/16450. If it is soldered, the swap means desoldering a 40-pin chip on an irreplaceable board.

### Gaps
- The Compaq Portable III Technical Reference Guide and a Portable III Maintenance and Service Guide were not found online (searched archive.org, bitsavers and minuszerodegrees via search; found only the Portable, Portable II, Portable 386 and Portable 486 guides).
- No VCFed or Vogons thread naming the Portable III's UART was found.
- I did not examine board photographs. The archive.org Operations Guide OCR text returned HTTP 500.
- Whether the Compaq BIOS or a `MODE SPEED`-style utility drops the CPU to 8 MHz during disk access was not checked. It matters for timing loops.

## What speeds are reliable on a 12 MHz 286 with a FIFO-less 16450? Is 115200 the ceiling?

### Takeaway
115200 is the hard ceiling of a standard PC UART (divisor 1), with 57600 and 38400 the only steps below it. Interrupt-driven software on FIFO-less UARTs is documented as topping out below 57600 on 286s, and a 2026 report shows an XT with a FIFO-less UART and an FTDI adapter failing at 115200 but working at 38400. No measured figure for a 12 MHz 286 with a 16450 was found; polling with interrupts off is the route with real precedent at 115200.

### Cited Findings
- Kermit 3.16's own baud table ends at 115200, and its divisor table gives 3 for 38400, 2 for 57600 and 1 for 115200. — [msxibm.asm lines 226-246 and 272-274, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- The divisor formula is 115200 / baud rate, so divisor 1 is the fastest setting. — [Wikibooks, Serial Programming/8250 UART Programming, search excerpt](https://en.wikibooks.org/wiki/Serial_Programming/8250_UART_Programming)
- Ralf Brown's port list says of the 8250A, 16450 and 16C451 used in ATs that "most chips run up to 115KBd". — [RBIL port 03F8-03FF, search excerpt](https://fd.lod.bz/rbil/ports/other/p03f803ff.html)
- Kermit's 1995 guidance: "On 386-class PCs with high-quality buffered UARTs, Kermit can be used at speeds up to 57600 bps under DOS (under Windows or DesqView, or on 286s or below, the maximum speed is usually lower). 115200 bps usually works only with a short shielded cable, and the async adapters of the two devices in perfect tune." — [KERMIT.BWR 3.14, section 11, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)
- Kermit's 1990 guidance, for terminal emulation: "For PC/ATs and PS/2s, it is generally 19200, perhaps 38400." This is the file dated 30 March 1990 for version 3.01. — [mskerm.bwr on the Utah mirror, read directly](https://ftp.math.utah.edu/public_html/pub/ibmpc/kermit/mskerm.bwr)
- "If your speed is set too high, the symptom might be lost or garbled characters or graphics images on the screen, or data-overrun beeps. Normally flow control prevents these problems so use it if you can." — [KERMIT.BWR 3.14, section 11, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)
- "Even when using RTS/CTS flow control, characters can be lost during file transfer. This can happen if the PC turns off interrupts for any length of time, e.g. to service the hard disk." TSRs, disk caches and screen savers are named as causes. — [KERMIT.BWR 3.14, section 17.2, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)
- Kermit's RTS/CTS guards its software buffer, not the UART: the receive buffer is 1536 bytes; the interrupt handler drops RTS when the buffer passes 3/4 full (1152 bytes) and the low-water mark is 1/4 (384 bytes). — [mssdef.h line 143 and msxibm.asm lines 41-42 and 7818-7832, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- A Tandy 1000SX (V20) with a 16450, running Telix or Procomm with RTS/CTS: "It seems to work fine at 115200." Chuck(G): "If there's handshaking involved, 115200 is perfectly doable." — [VCFed thread, 2021, read directly](https://forum.vcfed.org/index.php?threads/8088-and-modem-baud-rates-16450-uart.79806/)
- An IBM 5155 (8088, 4.77 MHz) with a FIFO-less VL16C452, linked to a Raspberry Pi 5 through an FTDI adapter and a null modem (thread dated 31 March to 5 April 2026): 115200 failed; at 19200 Telix ZMODEM worked with some retransmitted blocks; at 38400 terminal use, YMODEM and SLIP "worked reasonably well". A Prolific-based adapter was dropped in favour of the FTDI one. — [classic-computing.de (VzEkC) thread, read directly, German](https://forum.classic-computing.de/forum/index.php?thread/39299-funktionierende-slip-config-zwischen-pc-xt-8088-4-77mhz-und-raspberry-pi5-via-us/)
- The Navas modem FAQ says the 8250 and 8250A "are capable of speeds up to 115,200 bps", and that under MS-DOS an 8250/16450 can manage "19200-57600 bps (depending on the speed of the system processor) and well-written software". — [modemfaq.navasgroup.com, search excerpt](http://modemfaq.navasgroup.com/faq_b.htm)
- A Usenet thread has posters reporting an 8250 run at 115200 "without missing characters" on 10 MHz XT-class machines when nothing else interfered, and noting that a TSR that disables interrupts for about 2 ms loses data even on a 16550A at 115200. IDE block mode is given as an example of a long interrupts-off period. — [comp.os.msdos.misc "8250 UART vs. 16550 UART", search excerpt](https://groups.google.com/g/comp.os.msdos.misc/c/Zkm51tOxzdM)
- A 1991 Usenet poster reports rz/sz between 16550 machines and "a 286 using a 16450 at baud rates as high as 38400 baud". — [comp.unix.questions archive, search excerpt](https://www.tuhs.org/Usenet/comp.unix.questions/1991-March/017094.html)
- MS-DOS INTERLNK/INTERSVR accept `/BAUD:` values of 9600, 19200, 38400, 57600 and 115200, and the default is 115200. The `/V` switch "prevents conflicts with a computer's timer", for use when a serial connection makes one computer stop. — [computerhope.com INTERSVR reference, search excerpt](https://www.computerhope.com/intersvrexe.htm)
- A 1 MHz 6502 (Apple IIc) receives a continuous 115200 bps stream by polling: a byte arrives "about every 86-90 cycles" and handling one costs about 11 cycles. — [colino.net, read directly](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)

### Inferences
- **Arithmetic:** at 115200 8N1 a byte arrives every 86.8 microseconds, which is about 1,040 CPU clocks at 12 MHz (about 690 at 8 MHz). At 57600 it is 173.6 microseconds (about 2,080 clocks); at 38400, 260 microseconds (about 3,125 clocks). Top throughput is 11,520 bytes per second.
- **Inference:** there is no rate between 57600 and 115200, because the divisor goes from 2 to 1. If 115200 fails, the fallback is half speed.
- **Estimate:** a polled receive loop on the 286 (read status, test, read data, store, loop) costs roughly 40-60 clocks, about 5% of the 1,040-clock budget at 115200. That is a wider margin than the Apple IIc's 11 cycles in 86. The instruction timings are from memory of Intel's 286 tables and are not verified here.
- **Inference:** with a FIFO-less UART the danger is latency, not average speed. In interrupt-driven mode, the timer (IRQ0) and keyboard (IRQ1) outrank the serial interrupt (IRQ4), so any BIOS handler that runs longer than one byte time causes an overrun. That is the likely reason interrupt-driven terminal programs fail at 115200 on slow machines while tight polled loops succeed. A program that owns the machine can either mask everything and poll, or install its own very short timer and keyboard handlers.
- **Inference:** INTERLNK's timer-conflict switch fits a design that runs with interrupts masked during serial transfers, but I found no documentation of its internals.
- **Correction:** `graphics-research.md` quotes "generally 19200, perhaps 38400" as Kermit's documentation. That sentence is from the 1990 beware file for version 3.01. The 1995 file says 57600 at best on 386s and "usually lower" on 286s. Both point the same way: expect Kermit itself to top out around 38400 on this machine.
- **Correction:** `graphics-research.md` says "A 12 MHz 286 without a FIFO has done 57600 with ZMODEM; 115200 gave errors". I found no source for that. Treat it as unverified.
- **Inference:** Kermit's RTS/CTS fixes loss caused by its parser falling behind (the buffer fills, RTS drops). It does not fix loss caused by interrupts being held off, because the UART's single holding register overruns before the software sees anything. The 57600 failure measured in DOSBox could be either; only a test on the real machine with RTS/CTS on will tell.
- **Estimate:** going faster than 115200 needs a different crystal or UART, which is a hardware modification. The FTDI side would not be the limit.

### Gaps
- No authoritative description was found of how LapLink, FastLynx or INTERLNK receive at 115200 on XT/AT machines (polled or interrupt-driven, block size, acknowledgement scheme).
- Omen's DSZ documentation was not found.
- No measured maximum for a 12 MHz 286 with a 16450 was found, for either interrupt-driven or polled reception.
- The Google Groups thread returned HTTP 429, so its claims are from the search excerpt only.
- DOSBox serial timing versus a real 16450 was not researched.

## How does an FTDI FT232R/FT232B behave with RTS/CTS on Linux when streaming at 115200 to a FIFO-less receiver?

### Takeaway
The FTDI chip does RTS/CTS itself once Linux sets `CRTSCTS`, but FTDI's own figures allow up to 3 more characters after CTS drops, which a FIFO-less 16450 cannot absorb unless the PC keeps reading. Use CTS as a coarse brake and pace the stream with a block-and-acknowledge protocol; set the latency timer to 1 ms so key events from the Compaq are not held for 16 ms.

### Cited Findings
- With `CRTSCTS` set, the Linux driver sends the chip a set-flow-control request selecting RTS/CTS handshaking; the code comment reads "Set hardware-assisted flow control". — [ftdi_sio.c lines 2713-2737, read directly](https://raw.githubusercontent.com/torvalds/linux/master/drivers/usb/serial/ftdi_sio.c)
- The request's protocol bits are: B0 "Output handshaking using RTS/CTS", B1 "Output handshaking using DTR/DSR", B2 "Xon/Xoff handshaking". — [ftdi_sio.h lines 258-288, read directly](https://raw.githubusercontent.com/torvalds/linux/master/drivers/usb/serial/ftdi_sio.h)
- FTDI's FAQ says the device stops transmitting within zero to three characters after CTS# goes high, depending on what is in its buffer: "This potential 3 character overrun does occasionally present problems." It also says RTS# changes state when only the last 32 bytes of buffer space remain. — [FTDI support FAQ, search excerpt](https://www.ftdichip.com/old2020/Support/FAQs.htm)
- FTDI's FT232BM design guide is quoted as giving a latency of 0 to 3 characters between taking CTS# high and transmission stopping, and as saying the chip can take up to 30 more characters after RTS# goes high. — [mikrocontroller.net thread, search excerpt](https://www.mikrocontroller.net/topic/41536)
- A 2026 user report: RTS/CTS "does not really help" with FTDI chips against a FIFO-less XT UART, because they "buffer 2-3 bytes and react too slowly". The original poster later reported that `stty -F /dev/ttyUSB0 crtscts` did work at the lower speeds he settled on. — [classic-computing.de thread, read directly, German](https://forum.classic-computing.de/forum/index.php?thread/39299-funktionierende-slip-config-zwischen-pc-xt-8088-4-77mhz-und-raspberry-pi5-via-us/)
- FT232R buffer sizes conflict between datasheet revisions: the 2.x revisions give a 128-byte receive buffer and a 256-byte transmit buffer; version 1.04 and a distributor page give 256-byte receive and 128-byte transmit. — [FT232R datasheet copy, search excerpt](https://www.radiolocman.com/datasheet/pdf.html?di=35312)
- The latency timer value is read from the device at attach, with 16 ms as the fallback; the `ASYNC_LOW_LATENCY` flag forces 1 ms. — [ftdi_sio.c lines 1367-1380 and 2207-2212, read directly](https://raw.githubusercontent.com/torvalds/linux/master/drivers/usb/serial/ftdi_sio.c)
- A 2017 stable-kernel fix stopped the driver setting `ASYNC_LOW_LATENCY` by default, restoring the 16 ms device default; it suggests `setserial /dev/ttyUSB0 low_latency` for users who want 1 ms. — [LKML, search excerpt](https://lkml.iu.edu/hypermail/linux/kernel/1706.0/00749.html)
- The timer is exposed at `/sys/bus/usb-serial/devices/ttyUSBx/latency_timer`. One report says a new value does not take effect on a port that is already open. — [projectgus.com, search excerpt](https://www.projectgus.com/2011/10/notes-on-ftdi-latency-with-arduino/); [Granite Devices wiki, search excerpt](https://granitedevices.com/wiki/FTDI_Linux_USB_latency)
- Without an event, the chip returns received data only when its packet fills or the timer expires: the header describes the event character as making the device "immediately return the data read so far - rather than wait 40ms or until 62 bytes are read". — [ftdi_sio.h lines 339-346, read directly](https://raw.githubusercontent.com/torvalds/linux/master/drivers/usb/serial/ftdi_sio.h)
- FTDI documents that modem status line changes can be used to flush the chip's buffer on the FT232R, FT2232C and FT232BM. — [FTDI knowledgebase an232b_04flush, search excerpt](https://www.ftdichip.com/Support/Knowledgebase/an232b_04flush.htm)
- The driver sizes its transfers to the endpoint's maximum packet size. — [ftdi_sio.c lines 1591-1619, read directly](https://raw.githubusercontent.com/torvalds/linux/master/drivers/usb/serial/ftdi_sio.c)

### Inferences
- **Inference:** against a 16450, one byte arriving while the PC is not reading is an overrun. So the PC cannot drop RTS and walk away. It must keep reading for at least 3 to 4 more byte times after dropping RTS (about 350 microseconds at 115200), or the protocol must make the host stop on its own.
- **Inference:** the safer design is credit-based. The Pi sends one bounded block (a frame, or N bytes), then waits for a go-ahead byte from the Compaq. The Compaq sends that byte only when it is back in its receive loop. Colin Leroy-Mira's Apple II stream works this way (one byte from the client per frame).
- **Inference:** the Pi cannot stop a stream instantly from user space. Bytes already handed to the tty layer, in USB transfers, and in the chip's 128- or 256-byte buffer keep flowing. At 115200 the chip buffer alone is 11 to 22 ms of data. Keep writes small and bounded by the protocol.
- **Inference:** the latency timer only affects the Compaq-to-Pi direction. A lone scancode byte would wait up to 16 ms at the default. Set `latency_timer` to 1 before opening the port. Host-to-Compaq data is not delayed by it.
- **Inference:** with Kermit's own RTS/CTS, the 3-character overshoot is harmless: Kermit drops RTS with 384 bytes of buffer still free.
- **Estimate:** adapters sold as FTDI are sometimes clones, and their CTS response may differ. Measure this adapter.

### Gaps
- FTDI's application note AN232B-04, its FAQ and the FT232R datasheet all returned HTTP 403 to direct fetch. The 0-to-3-character figure is from search excerpts and is documented for the FT232BM; no FT232R-specific figure was found.
- No measurement exists for this adapter. A loopback test (send a counted stream, drop CTS, count what arrives) would settle it.
- Whether the owner's adapter uses an FT232R, FT232B or a later part is not known.
- Raspberry Pi 3 B+ USB host behaviour under continuous 115200 output was not researched.

## What does MS-DOS Kermit 3.16 itself support (APC, RUN, port state, speed, flow control, autodownload, Tektronix and sixel)?

### Takeaway
The plan works as designed: Kermit 3.16 accepts `ESC _ commands ESC \` from the host, and `SET TERMINAL APC UNCHECKED` lets that string `RUN` a DOS program, after which Kermit returns to terminal mode by itself. Kermit releases the UART before the program starts and leaves DTR and RTS asserted, so the Pi must stay silent until the program says it is ready.

### Cited Findings
**APC**
- MS-DOS Kermit 3.13 and later accept the APC sequence in the VT100-and-above emulators: `ESC _` string `ESC \` in 7-bit form. The string "can be any MS-DOS Kermit command or list of commands, separated by commas, and can be up to 1024 bytes in length". Kermit "executes the command(s) in the string and then automatically resumes CONNECT mode". — [KERMIT.UPD 3.14, section 10, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)
- "SET TERMINAL APC { ON, OFF, UNCHECKED }. OFF (the default) means Kermit will not execute any commands and will ignore APCs. ON means that Kermit will execute only commands that are relatively safe. UNCHECKED means Kermit will execute ANY commands sent via APC... UNCHECKED is required for RUN, i.e. to run DOS commands or external programs." — [KERMIT.UPD 3.14, section 10, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)
- The 3.16 source has the same three keywords (`off`, `on`, `unchecked`), with OFF as the default. — [msyibm.asm lines 207, 520-523 and 838-841, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- In 3.16 the APC text goes into a 1 KB buffer; a string longer than 1024 bytes is discarded. Commas outside curly braces become command separators. Kermit appends a carriage return and `C` (CONNECT) and runs the buffer as a macro. — [mszibm.asm lines 1932-2022, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- With APC ON (not UNCHECKED), 3.16 sets a trap flag that makes these commands fail: RUN, DELETE, OUTPUT, HANGUP, ENABLE, DISABLE, SET SERVER and SET TERMINAL APC itself. — [mssker.asm lines 2765 and 3080; mssscp.asm line 1991; mssset.asm lines 1956, 1967 and 3184; msxibm.asm line 7956; msyibm.asm lines 1588 and 3362-3364, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- RUN also fails if the hidden NOPUSH setting is on. — [mssker.asm lines 3080-3083, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)

**RUN, PUSH and the COM port**
- RUN passes the command line to the command processor with `/c` ("always use command.com"), so COMMAND.COM must be loadable. — [mssker.asm lines 3096-3120, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- Before the program starts, Kermit calls its suspend routine and then resets the serial port. Suspend tells the host to stop (sends XOFF, or with RTS/CTS flow control clears RTS), waits 20 ms, and resets the port. — [msxibm.asm lines 862-875 and the IHOSTS routine; mssker.asm lines 3123-3129, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- The port reset waits for the transmitter to empty, turns FIFO mode off, disables the UART's interrupts, restores the saved line control register, writes the modem control register as the saved value OR 3 (comment: "ensure DTR and RTS are asserted"), masks the IRQ at the interrupt controller and restores the original interrupt vectors. It does not touch the baud rate divisor. — [msxibm.asm lines 7523-7663, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- When the program exits, Kermit re-initialises the serial port and tells the host to resume. — [msxibm.asm "restore" routine following line 875, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- The documentation agrees: "when you PUSH to DOS (including when you use Kermit's RUN command), and you have XON/XOFF flow control enabled, Kermit sends an XOFF (Ctrl-S) to the host when you leave, and XON (Ctrl-Q) when you return (if you have RTS/CTS flow control enabled, Kermit turns off RTS)." — [KERMIT.BWR 3.14, section 11, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)
- DTR is lowered only by HANGUP: "In version 3.12 and later, the HANGUP command turns off DTR until the next time you issue a command that accesses the serial port." — [KERMIT.BWR 3.14, section 11, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)

**Speed and flow control**
- The highest SET SPEED value is 115200. — [msxibm.asm lines 226-246, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- SET FLOW-CONTROL accepts NONE, XON/XOFF, INCOMING-XON/XOFF, OUTGOING-XON/XOFF and RTS/CTS. — [mssset.asm lines 290-295, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- "Before giving the SET FLOW RTS/CTS command, be sure the current serial port is receiving the CTS signal -- use SHOW MODEM to check. If not, Kermit will hang for 10-15 seconds waiting for CTS to come on every time you type a character." — [KERMIT.BWR 3.14, section 6, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)
- Settings can be given on the DOS command line, comma-separated: `kermit set port 2, set speed 57600, set flow rts/cts, bsend bar.zip`. — [KERMIT.UPD 3.14, section 26, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)

**Autodownload**
- 3.16 has `SET TERMINAL AUTODOWNLOAD {ON, OFF}`: "ON to act upon incoming Kermit file transfer packets... Default is off". — [msyibm.asm lines 426, 784 and 842-843, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- In 3.13/3.14 automatic transfers were done through APC: the host sends `APC RECEIVE` and then sends the file. — [KERMIT.UPD 3.14, sections 10 and 26, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)

**Tektronix and sixel graphics**
- The Tektronix emulator understands: GS (vector plot mode, first move dark), RS (incremental plot), US and CR (leave plot mode), FF and ESC FF (erase), ESC Ctrl-Z (crosshair/GIN), dashed line patterns (ESC ` and a to e), rectangle draw and pattern fill (ESC / ... x, y, z), ANSI colour setting, and sixel (ESC P p1;p2;p3 q ... ESC \). — [msgibm.asm header comments lines 24-110, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- Coordinates are 4010 style (0-1023 in X and Y, with 0-780 visible in Y) or 4014 style (0-4095 with the extra low-order byte). — [msgibm.asm lines 124-131, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- On CGA the emulator uses BIOS mode 6 (640x200) and scales Tektronix coordinates by 640/1024 horizontally and 200/780 vertically. — [msgibm.asm lines 226, 1267 and 1498-1503, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- Sixel support: sixel characters 3Fh-7Eh drawn least significant bit at the top, `!` repeat counts, `$` (return to left margin), `-` (next row of six dots), and `#` colour selection. Raster attributes (`"`) are "all ignored for now". — [msgibm.asm lines 59-97, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- SET TERMINAL GRAPHICS choices in 3.16 include auto-sensing, CGA, EGA, VGA, Hercules, ATT and three Wyse-700 modes. — [msyibm.asm lines 598-607, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- The ATT choice is the AT&T 6300 / Olivetti M24 640x400 mode. Kermit sets BIOS mode 72 (48h, "Olivetti's Hi-res - 50 lines text"), uses segment B800h, and auto-detects by looking for the string "OLIVETTI" in the ROM. Toshiba T3100 (mode 74h) and DEC VAXmate (mode D0h) are treated "like Olivetti". — [msgibm.asm lines 231-233, 253 and 313-315, in msk316src.zip](https://www.kermitproject.org/msdoskermit/msk316src.zip)
- The Compaq selects its 400-line graphics with bit 0 of port 23C6h. — [seasip.info, read directly](https://seasip.info/VintagePC/compaq3.html)
- Kermit does not emulate ReGIS: the documentation points to a ReGIS-to-sixel converter instead. It also "does not emulate a particular kind of color Tektronix terminal, e.g. 41xx or 42xx series". — [KERMIT.BWR 3.14, section 12.6, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)
- On slow machines in a high-resolution graphics mode, Kermit "might not be able to keep up at speeds above 9600 bps" (said of the PS/2 Model 25 and 30). — [KERMIT.BWR 3.14, section 12.6, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)

**Program size**
- MS-DOS Kermit 3.15 executables: full version 251,768 bytes; medium (serial only, no networks) 199,356 bytes; "lite" versions 164,312 and 113,414 bytes. — [msk315.doc, in msk315.zip](https://www.kermitproject.org/msdoskermit/msk315.zip)

### Inferences
- **Inference (from the source; confirm on the virtual and real Compaq):** the handover is not protected by flow control. RTS is dropped for about 20 ms and then raised again by the port reset, and from then until the DOS program has set up the UART nobody is reading it. Anything the Pi sends in that window is lost. So: the Pi sends the APC, stops sending, and waits for a "ready" byte from the program at the new speed.
- **Inference:** DTR stays asserted across RUN, so with the full-handshake cable the Pi sees DSR/DCD stay up and nothing looks like a hang-up.
- **Inference:** Kermit does not restore the baud divisor when it releases the port, and it re-initialises the port at its own speed when the program exits. The program may set any speed it likes and need not put it back. The Pi must switch speed in step: up after sending the APC, down when the program signals exit.
- **Inference:** because Kermit appends CONNECT to the APC string, the terminal session resumes by itself when the program ends. No second command is needed.
- **Inference:** the APC command can be as simple as `run gfx.com`. The 1024-byte limit is not a constraint.
- **Estimate:** Kermit stays in memory while the program runs. With the full 3.15/3.16 build at roughly 250 KB plus DOS and a second COMMAND.COM, expect on the order of 250-300 KB free for the program in 640 KB. Measure with a test program.
- **Inference:** on a floppy-only system the disk holding COMMAND.COM must be in the drive when RUN executes, or COMSPEC must point somewhere reachable.
- **Inference (untested):** Kermit's 640x400 "ATT" graphics may not work on the Compaq. Kermit asks the BIOS for mode 48h and expects AT&T hardware; `graphics-research.md` gives the Compaq's mode as 40h and the Compaq uses its own port (23C6h). Try `SET TERMINAL GRAPHICS ATT` on the real machine before counting on Kermit sixel at 640x400.
- **Correction:** `graphics-research.md` says "With RTS/CTS flow control, Kermit can hold the Pi back instead of dropping data." True for the parser falling behind; not true for overruns caused by interrupts being off (see the speed section).

### Gaps
- The book "Using MS-DOS Kermit" (second edition PDF at kermitproject.org) was not read; it predates APC (it documents version 3.0/3.10).
- Columbia's own server returned HTTP 403 to direct downloads; the kermitproject.org copies were used.
- Which build of 3.16 is on the Compaq (full, medium or lite) was not checked. The lite builds have no terminal emulator.
- Behaviour was read from source, not run. The DOSBox rig can confirm the APC-to-RUN path and the modem-line states.

## What precedent exists for streaming graphics or video over a serial line to a vintage computer?

### Takeaway
The closest working precedent is Colin Leroy-Mira's Apple II video stream at 115200, and its design maps directly onto this plan. I found no published DOS program that streams frames over a serial port into video memory; the PC precedents are 1980s remote-control products and terminal graphics protocols.

### Cited Findings
**Apple II serial video (Colin Leroy-Mira, 2024)**
- The link is "a stable 115200bps", 11.52 kB/s. A raw 8 KB hi-res page would take about two-thirds of a second. — [colino.net, read directly](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)
- Frames are sent as byte-level differences. Control bytes have bit 7 set and set the write position (an offset, or a "base" when two arrive in a row); data bytes are stored in sequence. A repeat marker (FFh, count, value) is used for runs; short runs are sent as plain bytes because that was faster. — [colino.net, read directly](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)
- It double-buffers: each frame is diffed against the frame two steps back and written to the hidden page, which is then shown. — [colino.net, read directly](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)
- Pacing is per frame: the client sends one byte at each frame start (space pauses, escape stops). The server sleeps if a frame finished early for 24 fps and skips frames if the client falls more than one behind. No other flow control is described. — [colino.net, read directly](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)
- Ordered dithering was chosen because error diffusion changes nearly every pixel between frames and defeats the delta encoding. — [colino.net, read directly](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)
- Measured rates on a 1 MHz machine: about 7-8 fps at 280x192, 14-15 fps at 210x144, about 22 fps at 140x96 (the configured size). 24 fps full screen was not reached. — [colino.net, read directly](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)

**PC-side precedents**
- Carbon Copy Plus (Meridian Technology) linked two PCs' keyboards, screens and disks over ordinary phone lines with Hayes-compatible modems; its product sheet lists graphics support for CGA, EGA, VGA, Hercules and PS/2 formats. — [thecomputerarchive.com product sheet, search excerpt](https://www.thecomputerarchive.com/archivemain/Software/Utilities/Meridian%20Technology%20Carbon%20Copy%20Plus.PDF)
- Carbon Copy could "intercept and transmit both text and graphics in DOS applications". — [WinWorld, search excerpt](https://winworldpc.com/product/carbon-copy)
- Norton pcANYWHERE 4.5 (1992) offered "PC-to-PC remote computing via serial or modem connections". — [1992 press release at textfiles.com, search excerpt](https://discmaster.textfiles.com/view/10596/science%20library(b).zip/science%20library(b)/INFO/NETW92PR.ZIP/ANYWHERE.TXT)
- A 2026 report of the same hardware pattern (Raspberry Pi 5, FTDI adapter, null modem, 4.77 MHz XT with a FIFO-less UART) running SLIP with mTCP at 38400. — [classic-computing.de thread, read directly, German](https://forum.classic-computing.de/forum/index.php?thread/39299-funktionierende-slip-config-zwischen-pc-xt-8088-4-77mhz-und-raspberry-pi5-via-us/)
- GlyphBlaster (2026) streams 1-bit video to a CGA monitor from a Raspberry Pi Pico 2 W over Wi-Fi in UDP packets of 10 scanlines each. It drives the display directly; the PC and its serial port are not involved. — [martypc.blogspot.com, search excerpt](https://martypc.blogspot.com/2026/05/60fps-video-on-cga-glyphblaster.html)
- 8088 Domination plays 640x200 video on a 4.77 MHz 8088 from disk using inter-frame deltas, each a "slice" (differing bytes, written with REP MOVSB) or a "run" (identical bytes, REP STOSB). — [trixter.oldskool.org, read directly](https://trixter.oldskool.org/2014/06/19/8088-domination-post-mortem-part-1/)

**Terminal graphics protocols with DOS clients**
- RIPscrip: early versions "were tightly tied to the EGA 640x350" standard; the common v1.54 used 640x350 in 16 colours. — [Wikipedia, Remote Imaging Protocol, search excerpt](https://en.wikipedia.org/wiki/Remote_Imaging_Protocol)
- NAPLPS is resolution-independent, and a 1993 FAQ says terminal programs existed for "PC's with CGA, Herc monochrome, EGA, VGA". Prodigy's graphics used NAPLPS. — [NAPLPS FAQ at textfiles mirror, search excerpt](https://mirror.cyberbits.eu/textfiles.com/internet/FAQ/naplps.txt); [Wikipedia, Prodigy, search excerpt](https://en.wikipedia.org/wiki/Prodigy_(online_service))
- Sixel and Tektronix 4010/4014: supported by MS-DOS Kermit on CGA at 640x200 (details in the Kermit section). ReGIS: not supported by MS-DOS Kermit. — [KERMIT.BWR 3.14, section 12.6, in msk314.zip](https://www.kermitproject.org/msdoskermit/msk314.zip)

### Inferences
- **Inference:** the planned program has no direct published DOS equivalent that I could find. Its design can borrow the wire format and pacing from the Apple II project and the encoder ideas (ordered dither, slices and runs, a per-frame byte budget) from 8088 Domination.
- **Estimate, scaled from the Apple II measurements:** the link speed is identical (11.52 KB/s), so the bytes-per-frame budget carries over. The Apple's 280x192 screen is 7,680 bytes and reached 7-8 fps, so the stream averaged about 20% of raw. At the same ratio: 640x200 (16,000 bytes) gives about 3.5 fps; a 320x200 picture sent as 8,000 bytes and pixel-doubled on the Compaq gives about 7 fps; 640x400 (32,000 bytes) about 1.8 fps; 160x100 (2,000 bytes) is limited by other things, not the link. `graphics-research.md` estimates 5 fps at 640x200 for video; the Apple II data suggests 3-4 fps is the safer expectation.
- **Inference:** RIPscrip is ruled out by its EGA requirement. NAPLPS and Tektronix are vector formats and suit diagrams, not photographs or video.
- **Inference:** the remote-control products prove screen-over-serial was commercially practical on CGA at modem speeds far below 115200, but nothing found documents their protocols or update rates.

### Gaps
- No DOS serial video player, serial remote framebuffer or serial VNC-style client was found. The absence is from a small number of searches, not an exhaustive survey.
- Prodigy's DOS client resolution on CGA was not confirmed.
- ReGIS clients for DOS other than Kermit were not researched.
- Colin Leroy-Mira's later work adding sound was not read.

## Which compression can an 8088/286 decode at about 11 KB/s of input with little CPU?

### Takeaway
Decode speed is not the constraint: even a 4.77 MHz 8088 writes video memory about 20 times faster than 115200 baud delivers bytes. The constraint is that a FIFO-less UART must be read every 87 microseconds, so the format should be decodable in small bounded steps between reads; skip/copy/run opcodes in screen order fit that, and LZ4 or LZSA are options only if whole blocks are received first.

### Cited Findings
- On a 4.77 MHz 8088, "CGA RAM can only be changed at a rate of 240KB/s"; hard drives of the era deliver roughly 90 KB/s. — [trixter.oldskool.org, 8088 Domination post-mortem part 1, read directly](https://trixter.oldskool.org/2014/06/19/8088-domination-post-mortem-part-1/)
- Jim Leonard's 8088 LZ4 decompressor, timed on an IBM 5160 against a plain REP MOVSW copy of the same data: 0.76x the copy time on an RLE-heavy bitmap, 1.91x on a sparse bitmap, 2.16x-2.75x on compiled binaries, 3.17x on text, 1.39x on incompressible data. His target was "roughly 4x slower than a straight memory copy". — [trixter.oldskool.org, "A Case Study In Speed", read directly](https://trixter.oldskool.org/2013/01/18/optimizing-for-the-8088-and-8086-cpu-part-3-a-case-study-in-speed/)
- "It is actually faster to decompress such data than it is to merely copy it" (RLE-heavy bitmap). — [trixter.oldskool.org, read directly](https://trixter.oldskool.org/2013/01/18/optimizing-for-the-8088-and-8086-cpu-part-3-a-case-study-in-speed/)
- On the same test set PKWare's DCL took 7.75 seconds against 0.53 seconds for LZ4, "over 14 times slower"; PKUNZIP's Explode was 5.8x to 116x the copy time. — [trixter.oldskool.org, read directly](https://trixter.oldskool.org/2013/01/18/optimizing-for-the-8088-and-8086-cpu-part-3-a-case-study-in-speed/)
- The speed-optimised LZ4 routine is 436 bytes (180 of code plus a 256-byte table). A size-optimised version is "30% slower on average, but it compiles to only 78 bytes". — [trixter.oldskool.org, case study, read directly](https://trixter.oldskool.org/2013/01/18/optimizing-for-the-8088-and-8086-cpu-part-3-a-case-study-in-speed/); [trixter.oldskool.org, "LZ4 on the 8088: one small drop", read directly](https://trixter.oldskool.org/2013/02/09/lz4-on-the-8088-one-small-drop/)
- LZSA's published comparison on 8-bit test files: LZSA2 52.49% of original size at 75% of LZ4's decompression speed; LZSA1 57.08% at 90%; LZ4_HC 60.59% at 100%; ZX7 53.30% at 47.73%. The project includes an "8088 speed-optimized decompressor by Jim Leonard". — [github.com/emmanuel-marty/lzsa, read directly](https://github.com/emmanuel-marty/lzsa)
- LZSA commit notes for the 8088 decoders: LZSA1 with options `-f1 -m5` decompresses at a speed "comparable to LZ4"; the LZSA2 decoder is "roughly 50% faster than ZX7"; a jump-table rewrite of LZSA1 is 12.7% faster and under 3K. — [LZSA commit mirror, search excerpt](https://git.applefritter.com/6502/lzsa/commits/branch/master/asm/8088)
- The Apple II stream uses a format with no dictionary at all: position bytes, literal bytes and a repeat marker, at about 11 cycles of work per byte on a 6502. — [colino.net, read directly](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)
- 8088 Domination orders its deltas and gives each frame a "byte pool" and a "cycle pool"; deltas that would exhaust either are skipped. Error-diffusion dithering "is not a good idea for a system that is going to be recording changes between frames". — [trixter.oldskool.org, read directly](https://trixter.oldskool.org/2014/06/19/8088-domination-post-mortem-part-1/)
- CGA graphics memory is interlaced: even rows from offset 0, odd rows 8 KB higher, 80 bytes per row at 640x200. — [seasip.info CGA notes, search excerpt](https://www.seasip.info/VintagePC/cga.html)

### Inferences
- **Estimate:** a 12 MHz 286 moves memory several times faster than a 4.77 MHz 8088, so plain copies into video memory should exceed 1 MB/s and LZ4-class decoding several hundred KB/s. No 286 measurement was found; the point is only that both are far above the 11.5 KB/s the cable delivers.
- **Inference:** choose the format for compression ratio and for how it interleaves with reception, not for decode speed.
- **Inference:** in a polled design every decode step between two UART reads must finish inside one byte time (about 1,040 clocks at 12 MHz). Literal bytes are trivial. A long run fill or copy must be capped per step (on the order of 100-200 bytes, by my estimate from 286 string-instruction timings recalled from memory), or done as the bytes arrive. Opcodes of the form "skip N", "N literal bytes follow" and "repeat value N times" in video-memory order meet this naturally.
- **Inference:** LZ4 and LZSA are block formats with back-references. They fit a two-phase scheme: receive a whole compressed block into RAM with nothing else going on, signal the host to pause, decompress, signal go. That costs link idle time, so they pay off only if they compress frame deltas much better than skip/copy/run does. No measurement of that was found.
- **Inference:** prefer "write these bytes here" deltas over XOR deltas. `graphics-research.md` proposes XOR-delta and says a dropped frame never corrupts the picture; with XOR, one lost or corrupted byte leaves a permanent error until a full refresh, whereas replace-style deltas repair themselves the next time that area changes. Add a periodic full frame or a per-frame check byte either way.
- **Inference:** the encoder on the Pi should lay bytes out in the Compaq's memory order (interlaced banks) so that the client only ever writes forward.

### Gaps
- No absolute throughput figures (KB/s) for LZ4 or LZSA on an 8088 or a 286 were found; Jim Leonard's figures are relative to a memory copy on a 4.77 MHz machine.
- The LZ4_8088 page at oldskool.org refused connections.
- No benchmark of any decompressor on a 286 was found.
- No published comparison of skip/copy/run encoding against LZ over frame deltas for 1-bit dithered video was found.
- The Compaq 640x400 mode's four-bank memory layout (from `graphics-research.md`) was not re-verified here.
