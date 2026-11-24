# Compaq Portable III: expansion options and the DOS networking stack (as of 2026-10-13)

How to read these notes:

- **[sourced]** = stated by the linked page, which I fetched and read in this pass.
- **[snippet]** = seen only in a search-result summary; the page itself could not be opened (VOGONS and two other sites refused connections from this environment). Treat as weaker.
- **[derived]** = I worked it out from a linked primary file (for example by tracing net names in a KiCad schematic, or reading source code). The file is real; the reading is mine.
- **[estimate]** = my own arithmetic or judgement. Not from a source.
- **[not re-read]** = a source cited by the earlier doc that I did not open again.
- Claims from `docs/graphics-research.md` are checked under each question as **Earlier-doc check**.

Primary documents used most:

- Compaq Portable III Operations Guide, OCR text: <https://archive.org/details/compaq-portable-3-operations-user-manual> (full text file: <https://archive.org/download/compaq-portable-3-operations-user-manual/Compaq%20Portable%203%20Operations%20User%20Manual_djvu.txt>)
- Compaq Portable III Product Bulletin, First Edition, Feb 1987: <https://minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Product%20Bulletin%20-%20First%20Edition%20(FEB87).pdf>
- Community reverse-engineering repo (KiCad): <https://github.com/raymondh2/CompaqPortableIII>
- mTCP home page and manual (2026-10-10): <http://www.brutman.com/mTCP/mTCP.html>, <http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf>

---

## 1. The Portable III's expansion: rear connector, internal modem slot, Compaq's expansion unit, rarity, replicas

### Takeaway

The rear connector is a 96-pin DIN 41612 that carries almost the whole 16-bit AT (ISA) bus; Compaq's expansion unit (two 8 MHz 8/16-bit slots, sold as "2662A" on its label) adds only a -5 V regulator, a 14.318 MHz oscillator and one buffer chip, so a home-made ISA breakout is electrically simple, but nobody sells one. The internal modem slot is not ISA: it is a 24-pin, single-chip-select, 8-register port meant for one UART, and Compaq itself sold a "second serial port" board for it.

### Cited Findings

**Compaq's own description of the expansion unit**

- [sourced] The machine has no internal slots; the bulletin lists "optional expansion unit with 2 full-size industry standard expansion slots" — [Product Bulletin, p. 3](https://minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Product%20Bulletin%20-%20First%20Edition%20(FEB87).pdf)
- [sourced] Slot specification, read from the page image: "Two, 8 MHz 8/16-bit slots (fully skirted 8-bit boards not compatible)". Dimensions 6.0 x 2.4 x 14.5 in (15.2 x 6.1 x 36.8 cm) — [Product Bulletin, p. 14](https://minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Product%20Bulletin%20-%20First%20Edition%20(FEB87).pdf); same dimensions in [Operations Guide, Table A-4](https://archive.org/details/compaq-portable-3-operations-user-manual)
- [sourced] "Regardless of the speed at which the COMPAQ PORTABLE III Personal Computer operates, the boards in the optional expansion unit always run at 8 MHz." — [Operations Guide, section 2.11](https://archive.org/details/compaq-portable-3-operations-user-manual)
- [sourced] Compaq part number for the Expansion Unit is 107334-001 (item number 267). The bulletin does not use the name "2662A" — [Product Bulletin, p. 15](https://minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Product%20Bulletin%20-%20First%20Edition%20(FEB87).pdf)
- [sourced] "Model 2662A", a 96-pin port, power drawn from the computer, and a $199 list price come from Wikipedia, which cites oldcomputers.net, Byte (May 1987) and a Tripod page — [Wikipedia: Compaq Portable III](https://en.wikipedia.org/wiki/Compaq_Portable_III)
- [sourced] The power supply was sized for it: 145 W steady / 160 W peak, "Prevents replacing or supplementing existing power supply to add expansion unit" — [Product Bulletin, p. 7](https://minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Product%20Bulletin%20-%20First%20Edition%20(FEB87).pdf)
- [sourced] Compaq boards intended for the unit: Enhanced Color Graphics Board (EGA) and an "Asynchronous Communications/Parallel Printer Board" (extra COM1/COM2 and LPT1-3) — [Operations Guide, ch. 8](https://archive.org/details/compaq-portable-3-operations-user-manual)
- [sourced] A second clip-on unit existed: the "40-Megabyte Fixed Disk Drive Backup Expansion Unit" (DC-2000 tape). It is not an ISA box — [Operations Guide, ch. 8](https://archive.org/details/compaq-portable-3-operations-user-manual)
- [sourced] John Elliott's page confirms only that the rear connector exists and that the unit "contains the ISA slots"; it gives no pinout — [seasip.info](https://seasip.info/VintagePC/compaq3.html)

**What the rear 96-pin connector is electrically (community schematic)**

- [derived] The repo's `CompaqPortableISACHASSIS` schematic uses a DIN 41612 96-pin connector (3 rows x 32, male, horizontal) feeding two 16-bit ISA edge slots — [KiCad schematic](https://github.com/raymondh2/CompaqPortableIII/blob/main/CompaqPortableISACHASSIS/CompaqPortableISACHASSIS.kicad_sch). Tracing its net labels gives this pin assignment (author's naming; BAxx = SA address, DBx = SD0-7, Dxx = SD8-15, IO = I/O channel check, IO_READY = IOCHRDY):
  - Row a: 1 DB7, 2 +5V, 3 DB4, 4 DRQ2, 5 DB1, 6 +12V, 7 AEN, 8 +5V, 9 BA17, 10 /DACK3, 11 BA14, 12 DRQ1, 13 BA11, 14 IRQ7, 15 BA08, 16 IRQ4, 17 BA05, 18 TC, 19 BA02, 20 +12V, 21 SBHE, 22 /IOCS16, 23 LA21, 24 IRQ12, 25 LA18, 26 /DACK0, 27 /MEMW, 28 DRQ5, 29 D10, 30 /DACK7, 31 D13, 32 D15
  - Row b: 1 GND, 2 DB6, 3 IRQ2, 4 DB3, 5 -12V, 6 DB0, 7 GND, 8 BA19, 9 /IOW, 10 BA16, 11 DRQ3, 12 BA13, 13 /REFRESH, 14 BA10, 15 IRQ6, 16 BA07, 17 IRQ3, 18 BA04, 19 ALE, 20 BA01, 21 GND, 22 LA23, 23 IRQ10, 24 LA20, 25 IRQ15, 26 LA17, 27 DRQ0, 28 D8, 29 /DACK6, 30 D11, 31 DRQ7, 32 MASTER
  - Row c: 1 IO (IOCHCK), 2 RESET, 3 DB5, 4 GND, 5 DB2, 6 0WS, 7 IO_READY, 8 /FIRSTMB, 9 BA18, 10 /IOR, 11 BA15, 12 /DACK1, 13 BA12, 14 SYSCLK, 15 BA09, 16 IRQ5, 17 BA06, 18 /DACK2, 19 BA03, 20 +5V, 21 BA00, 22 /MEMCS16, 23 LA22, 24 IRQ11, 25 LA19, 26 IRQ14, 27 /MEMR, 28 /DACK5, 29 D9, 30 DRQ6, 31 D12, 32 D14
- [derived] Not on the connector, and recreated inside the chassis in that schematic: -5 V (an L7905 regulator fed from -12 V), OSC (a DIP-14 crystal oscillator), /SMEMR and /SMEMW (a 74LS125 gating /MEMR and /MEMW with /FIRSTMB), and the slot CLK (SYSCLK through the same 74LS125) — [same schematic](https://github.com/raymondh2/CompaqPortableIII/blob/main/CompaqPortableISACHASSIS/CompaqPortableISACHASSIS.kicad_sch)
- [derived] Only three pins carry +5 V (a2, a8, c20), two carry +12 V, one carries -12 V, four carry ground — [same schematic](https://github.com/raymondh2/CompaqPortableIII/blob/main/CompaqPortableISACHASSIS/CompaqPortableISACHASSIS.kicad_sch)
- [sourced] Reliability caveat from the author: "The mainboard schematics are not verfied or complete." The README lists the status of the other boards but says nothing about the ISA chassis — [repo README](https://github.com/raymondh2/CompaqPortableIII)

**Modern replicas, adapters, breakouts**

- [sourced] The only replica work found is that repo (26 commits, Aug 2022 to May 2024, CERN OHL-S v2). Stated status: "Current PCB Memory Expansion board layout is untested. The backplane for the expansion cards is tested and working." — [repo README](https://github.com/raymondh2/CompaqPortableIII)
- [derived] The "tested and working" backplane is the **internal** memory/modem backplane, not the ISA unit: its connectors carry DRAM address, RAS/CAS and MODEM_* nets, and its PCB is routed (975 track segments, Gerbers included) — [backplane folder](https://github.com/raymondh2/CompaqPortableIII/tree/main/CompaqPortableIIIexpansionbackplane)
- [derived] The ISA chassis design is a schematic only: its PCB file has 17 footprints placed and zero track segments, no Gerbers, last touched 2022-08-24 — [chassis folder](https://github.com/raymondh2/CompaqPortableIII/tree/main/CompaqPortableISACHASSIS)
- [sourced] The same README links one other modern part, a replacement battery module by Sergey Kiselev — [skiselev/compaq-portable-iii-battery](https://github.com/skiselev/compaq-portable-iii-battery)
- [snippet] A VOGONS thread ("A new (old) Toy - Compaq portable III") points readers to the raymondh2 repo as an expansion-card recreation, and one poster planned to trace the internal connector pinout from an original box — [VOGONS](https://www.vogons.org/viewtopic.php?p=1372767)

**The internal memory/modem slot**

- [sourced] The memory board "includes MEMORY/MODEM INTERFACE"; a separate "16-Bit Memory/Modem Interface Board" was sold for machines that wanted the modem without memory. Maximum RAM 6.6 MB (three 2 MB kits) or 2.1 MB (three 512 KB kits) — [Product Bulletin, p. 10](https://minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Product%20Bulletin%20-%20First%20Edition%20(FEB87).pdf); [Operations Guide, ch. 8](https://archive.org/details/compaq-portable-3-operations-user-manual)
- [derived] The modem position on the backplane is a 24-contact connector (TE 5530843-1): 1 GND, 2 +5V, 3-10 MODEM-DB0..7, 11 MODEM_CS, 12 MODEM_IRQ, 13 /XIOW, 14 /XIOR, 15 MR (reset), 16 Speaker, 17-19 SA0-SA2, 20 n/c, 21 +12V, 22 -12V, 23 +5V, 24 GND. The 8 data lines are buffered from SD0-7 by a 74LS245 enabled by MODEM_CS — [backplane schematic](https://github.com/raymondh2/CompaqPortableIII/blob/main/CompaqPortableIIIexpansionbackplane/CompaqPortableIIIexpansionbackplane.kicad_sch), [BOM](https://github.com/raymondh2/CompaqPortableIII/blob/main/CompaqPortableIIIexpansionbackplane/BOM.csv)
- [sourced] Compaq made a non-modem board for this slot: "The Second Asynchronous Communications Interface Board provides one additional asynchronous communications interface if an internal modem is not installed ... installed in the modem slot. This is an international option available only outside the U.S. and Canada." — [Operations Guide, p. 8-12](https://archive.org/details/compaq-portable-3-operations-user-manual)
- [sourced] seasip.info describes the same arrangement: two daughterboard connectors, one for video, the other for "an optional memory expansion and/or a modem" — [seasip.info](https://seasip.info/VintagePC/compaq3.html)

**Rarity and price in 2026**

- [sourced via search listing] eBay item "RARE Compaq Portable III ISA Expansion Box 2662A": asking US $375 with best offer; the page noted one already sold. I could not open the listing (HTTP 403) — [eBay 315972513715](https://www.ebay.com/itm/315972513715)
- [snippet] A Compaq Portable 386 (model 2670) bundled with a 2662A box sold for US $400 (page shows "Wed, 1 Jul", no year) — [eBay 127550180353](https://www.ebay.com/itm/127550180353)
- [snippet] A complete Portable III (model 2660) with 2662A, untested with a disk error, was listed at $80 Buy It Now — [PicClick](https://picclick.com/Compaq-Portable-III-2660-w-2662A-Powers-112611112972.html); another system-plus-chassis sale is archived at [WorthPoint](https://www.worthpoint.com/worthopedia/compaq-portable-iii-2660-external-1818383218)
- [sourced] German hobbyists report owning units (one bought from a former utility worker with a serial/parallel card inside), so they do circulate in Europe too — [DOSReloaded thread, 2017](https://dosreloaded.de/forum/thread/489-compaq-portable-iii-restauration-upgrades/)

### Inferences

- [estimate] The same 2662A box is sold with both the Portable III and the Portable 386 (the $400 bundle), so searching for either machine "with expansion" doubles the supply. Buying a whole untested machine with the box attached can be cheaper than the box alone ($80 versus about $375-400).
- [estimate] Expect $300-450 for a bare 2662A in 2026 when one appears; I found three data points, not a price history.
- [estimate] A DIY two-slot breakout is feasible for someone who can lay out a PCB: one DIN 41612 connector, two ISA edge sockets, an L7905, a 14.318 MHz can oscillator and a 74LS125. Parts cost roughly $20-30 plus the board. The risks are that the published schematic is unverified and the mating connector gender and mechanical fit must be checked on the real machine. A card that needs neither -5 V nor OSC (PicoMEM-class cards are 5 V only) would need even less.
- [estimate] With only three +5 V pins, keep a home-made box to a couple of amps; two modern low-power cards are fine, old full-length cards may not be.
- [estimate] The modem slot is the cheapest unexplored expansion point. It already supplies a decoded chip select, IRQ, 8 data bits and three address lines, which is exactly a 16550-class UART footprint. A small board with a 16550A (or a microcontroller pretending to be one) would be a second, FIFO-equipped COM port without the expansion unit. It means removing the modem, and nobody has published such a board.
- **Earlier-doc check.** "2662A Expansion Unit adds two 8/16-bit ISA slots (run at 8 MHz). It's rare." Confirmed by Compaq's bulletin and Operations Guide; add the "fully skirted 8-bit boards not compatible" limit and the Compaq part number 107334-001.

### Gaps

- No Compaq-published pinout was found. The Technical Reference Guide (Compaq P/N 107303-001) would have it; an 86Box contributor said in Dec 2024 they could not find that guide either — [86Box issue 5011](https://github.com/86Box/86Box/issues/5011).
- I could not confirm from a Compaq document that the rear connector is DIN 41612; that comes from the community schematic and Wikipedia's "96-pin port".
- No Tindie, Hackaday or VCFed project for a finished ISA breakout turned up. VOGONS pages could not be opened from here, so a recent thread could have been missed.
- eBay sold-price history could not be read directly (403); the figures above are from search listings.
- I did not find the 2662A's own service documentation.

---

## 2. If ISA were available: which cards give the most, requirements on a 286, 2026 prices

### Takeaway

A PicoMEM is the single most useful card: Wi-Fi NE2000, 4 MB of EMS, disk and floppy images from microSD, and USB mouse, on an 8-bit card that is known to work in a Compaq Portable II (286) and prefers slow 8 MHz buses like this one. It costs $59.99 (v1.1) or $89.99 (PicoMEM 2) at TexElec today. A plain NE2000-class card gives the fastest network link (hundreds of KB/s).

### Cited Findings

**PicoMEM**

- [sourced] Features: RAM emulation in 16 KB steps, 4 MB EMS, its own BIOS, 2 floppy and 4 hard-disk images (up to 4 GB each) from microSD, USB mouse and joystick, NE2000 emulation over Wi-Fi (Pico W models), AdLib/CMS/Tandy/Covox sound — [FreddyVRetro/ISA-PicoMEM](https://github.com/FreddyVRetro/ISA-PicoMEM)
- [sourced] It is an 8-bit card using the 8-bit memory and I/O bus plus one IRQ. IRQ choices: 3 or 5 (rev 1.0), 2, 5 or 7 (rev 1.1), 3/5/6/7 (PicoMEM 2). The NE2000 defaults to IRQ 3 — [same](https://github.com/FreddyVRetro/ISA-PicoMEM)
- [sourced] 286 compatibility: "Compaq Portable 2 (286): Ok"; "Worked on Various 486, 386, 286 (Has more chance to work with lower ISA Clocks)"; "Fail on some fast 286 (16MHz)" — [same](https://github.com/FreddyVRetro/ISA-PicoMEM)
- [sourced] Wi-Fi limits: credentials go in `wifi.txt`; v1.x has an on-board antenna inside the case so "the connection quality may be low"; PicoMEM 2 has an external antenna. No throughput figure is published — [same](https://github.com/FreddyVRetro/ISA-PicoMEM)
- [sourced] Direct SD/USB file access uses a network redirector that needs DOS 3.2 or later — [same](https://github.com/FreddyVRetro/ISA-PicoMEM)
- [sourced] PicoMEM 2 differences: RP2350B at 360 MHz, zero-wait RAM raised from 128 KB to 256 KB, PSRAM with 1 wait state, OPL3, DAC, RTC, USB-A, OLED, CD-ROM emulation, GUS support — [same](https://github.com/FreddyVRetro/ISA-PicoMEM)
- [sourced, read 2026-10-13] Prices: PicoMEM v1.1 $59.99, in stock — [TexElec](https://texelec.com/product/picomem/). PicoMEM 2 $89.99, in stock — [TexElec](https://texelec.com/product/picomem-2/). Other sellers named by the author: Serdashop (EU), Flamelily (UK) — [README](https://github.com/FreddyVRetro/ISA-PicoMEM)

**NE2000-class Ethernet, measured with mTCP's SpdTest (upper bounds, no disk)**

- [sourced] 8088 at 4.77 MHz, NE2000 clone: 54.7 send / 59.2 receive KB/s. 8086 at 8 MHz (PS/2 Model 25), 3Com 3C503: 188.2 / 191.3 KB/s. AT&T 6300 (8086 at 8 MHz), SMC Elite16: 163 / 165 KB/s. 386DX-40, 16-bit NE2000-compatible: 700 / 1005 KB/s — [mTCP performance notes](http://brutmanlabs.org/mTCP/mTCP_Performance.html)
- [sourced] "Real world performance, especially when using a disk, will be much lower." — [same](http://brutmanlabs.org/mTCP/mTCP_Performance.html)
- [sourced] For comparison, the parallel-port Xircom PE3-10BT on the same table: 42.9 send / 22.8 receive (8088, standard port), 87.5 / 53.1 (8086 at 8 MHz), 189 / 104 (386DX-33, standard port). It "will receive data at half the send rate" on a standard (not bidirectional) port — [same](http://brutmanlabs.org/mTCP/mTCP_Performance.html)

**PicoGUS and others**

- [snippet] PicoGUS is a sound card (GUS, AdLib, others) priced around "$50 / EUR 65 / GBP 58" in an undated write-up; the designer no longer sells on Tindie and points to picog.us for sellers — [RetroRGB](https://retrorgb.com/?p=48575), [Tindie](https://www.tindie.com/products/polpo/picogus-femto-edition-for-hand386-and-isa)
- [sourced] German owners suggest an ISA CompactFlash (XT-CF style) card for the box; one owner could not get CHS translation to work with CF on the built-in IDE port because the BIOS only accepts its fixed drive-type table — [DOSReloaded thread](https://dosreloaded.de/forum/thread/489-compaq-portable-iii-restauration-upgrades/); the fixed 47-entry type table is documented at [seasip.info](https://seasip.info/VintagePC/compaq3.html)

### Inferences

- [estimate] On this 286-12 with an 8 MHz bus, a real 16-bit NE2000 clone should land between the 8 MHz 8086 figure and the 386DX-40 figure: roughly 200-500 KB/s raw. That supports the earlier doc's "250-450 KB/s" estimate; it remains an estimate.
- [estimate] The PicoMEM changes the memory picture, which matters more than raw link speed for "more powerful programs". This machine has no EMS and no extended memory at 640 KB (Compaq's own CEMM "cannot be used in conjunction with the 12-MHz 80286" — [Product Bulletin, p. 16](https://minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Product%20Bulletin%20-%20First%20Edition%20(FEB87).pdf)). 4 MB of EMS lets MicroWeb load bigger pages and images.
- [estimate] DOS 3.1 limits: the PicoMEM's SD/USB redirector needs DOS 3.2+, so on DOS 3.1 use its BIOS-level disk images (which need no DOS support) or boot a newer DOS from a PicoMEM disk image.
- [estimate] IRQ clash to plan for: the internal modem sits on COM2 (IRQ 3) by default (see question 3), and the PicoMEM's NE2000 also defaults to IRQ 3. Use IRQ 5 or 7 on the PicoMEM, or disable the modem's port with the system-board jumper.
- [estimate] "Fully skirted 8-bit boards not compatible" does not affect PicoMEM-style short cards, but rules out some old 8-bit cards whose lower edge extends past the 8-bit connector.
- [estimate] A PicoGUS adds sound only; it does nothing for links or program size. Its 286 compatibility was not confirmed in anything I read.
- [estimate] Used NE2000-compatible ISA cards are common and cheap (roughly $15-40 on eBay); I did not verify current listings.
- **Earlier-doc check.** "PicoMEM (Pi Pico W with Wi-Fi networking, $60-90)": confirmed against today's TexElec prices. "Xircom PE3-10BT ... 23-53 KB/s receive on 8088/8086s": confirmed against mTCP's table.

### Gaps

- No published throughput for PicoMEM's Wi-Fi NE2000 emulation.
- No report of a PicoMEM in a Portable III expansion unit specifically (only the Portable II).
- Current PicoGUS price and 286 compatibility were not verified.
- NE2000 card prices are unverified.

---

## 3. The internal modem option: what it is, which COM port, and whether it matters

### Takeaway

The internal modem is a Hayes-compatible 300/1200 baud unit (a 2400 baud version came later) with its own UART; it defaults to COM2 and leaves the 9-pin port as COM1, so it does not get in the way of serial software unless someone moved it with the system-board jumpers. It is useless as a link today, but its slot is valuable.

### Cited Findings

- [sourced] At launch: "Internal Modem - Hayes-compatible - 300/1200 Baud - Tone/pulse dialing - Full- or half-duplex - Auto answer/originate". Stated benefit: "Frees asynchronous communications interface for other serial devices". Type: 0-300 baud Bell 103J, 1200 baud Bell 212A. Compaq P/N 107329-001 — [Product Bulletin, pp. 8, 14, 15](https://minuszerodegrees.net/manuals/Compaq/Compaq%20Portable%20III%20-%20Product%20Bulletin%20-%20First%20Edition%20(FEB87).pdf)
- [sourced] The later Operations Guide lists two kits. 1200: "compatible with Bell 103J and 212A standards for 300 baud and 1200 baud ... CCITT V.22 ... provides one RJ11 (CA11 in Canada) telephone jack." 2400: "Bell 103J and CCITT V.21 at 300 Baud, Bell 212A and CCITT V.22 at 1200 Baud, and CCITT V.22 at 2400 Baud" (that is the manual's wording; 2400 is normally V.22bis) — [Operations Guide, p. 8-6](https://archive.org/details/compaq-portable-3-operations-user-manual)
- [sourced] Port assignment. Section 7.4: "Refer to the configuration label on the inside rear of the computer for the locations and settings of the jumpers that change the default of COM2 by the modem to COM1 if this is required by your communications software." Section 7.1 lists what the switch and jumpers can do, including "Change the modem from COM1 to COM2" and "Disable either COM1, COM2, or both asynchronous communications interfaces." — [Operations Guide, ch. 7](https://archive.org/details/compaq-portable-3-operations-user-manual)
- [sourced, lower confidence] TH99's board entry gives jumper names: E3/E4 select "COM1 Serial / COM1 Modem / COM2 Serial / COM2 Modem" and E5/E16 select "COM1/IRQ4" or "COM2/IRQ3" for serial or modem. The same page wrongly calls the video connector "VGA", so treat its details with care — [TH99](https://th99.classic-computing.de/m/C-D/32736.htm)
- [derived] The modem connector has its own chip select (MODEM_CS) and interrupt line (MODEM_IRQ) and only three address lines, so the modem carries its own UART and is a separate COM port, not a tap on the external one — [backplane schematic](https://github.com/raymondh2/CompaqPortableIII/blob/main/CompaqPortableIIIexpansionbackplane/CompaqPortableIIIexpansionbackplane.kicad_sch)
- [derived] The on-board serial port in the community schematic is a single 16450 (U30) clocked by a 1.8432 MHz oscillator (U44), with MC1488/MC1489 line drivers to the DE-9 — [Serial.kicad_sch](https://github.com/raymondh2/CompaqPortableIII/blob/main/compaqportableIII_mainboard/Serial.kicad_sch); the author marks the mainboard schematics "not verfied or complete" — [README](https://github.com/raymondh2/CompaqPortableIII)

### Inferences

- [estimate] Default layout: 9-pin port = COM1 (3F8h, IRQ 4); modem = COM2 (2F8h, IRQ 3). The current Kermit setup already proves which port the cable is on. To check the modem, run `DEBUG`, then `D 40:0 L8`: the first words are the BIOS's COM1-COM4 base addresses.
- [estimate] Consequences for serial software: none for COM1 users (Kermit, EtherSLIP `ethersl 0x60 4 0x3f8 ...`, EPPPD `com1`). The modem does occupy IRQ 3, which matters only if an ISA card wants IRQ 3.
- [estimate] The fitted modem implies the machine has either the memory expansion board or the 16-Bit Memory/Modem Interface Board inside. If it is the memory board with empty module sites, RAM beyond 640 KB is a matter of finding Compaq-format modules; the repo's untested memory-board recreation uses 30-pin SIMM sockets ([BOM](https://github.com/raymondh2/CompaqPortableIII/blob/main/CompaqPortableIIImemexp/BOM.csv)).
- [estimate] A 1200 or 2400 baud modem is slower than the current 9600 baud cable and needs a phone-line simulator to talk to anything, so it adds nothing as a link.
- **Earlier-doc check.** "The UART chip isn't documented for the Portable III ... The Portable 386 has a 16450": the community schematic now shows a 16450 for the Portable III too (unverified by its author). That confirms "no FIFO". A 16550A is generally a drop-in for a 16450 in a DIP-40 socket, but I did not verify that this chip is socketed or even a DIP on this board.
- **Earlier-doc check.** "A 25-pin printer port; whether it's bidirectional is unknown": in the same repo's parallel-port sheet the data latch is a 74LS374 with its output-enable pin tied to ground, which means the data lines are output-only ([Parallel Port.kicad_sch](https://github.com/raymondh2/CompaqPortableIII/blob/main/compaqportableIII_mainboard/Parallel%20Port.kicad_sch), derived, unverified schematic). Plan on nibble-mode (4-bit) input for LapLink cables and Xircom adapters.

### Gaps

- The two Operations Guide sentences disagree on direction ("default of COM2 ... to COM1" versus "from COM1 to COM2"); the configuration label inside the rear panel is the authority for a given machine.
- Which modem (1200 or 2400) is in this machine is unknown; the faceplate or `ATI` response would tell.
- No documentation of the modem's chipset or of the Second Asynchronous Communications Interface Board's circuit was found.

---

## 4. Networking over the serial cable: SLIP and PPP packet drivers, speeds on a FIFO-less UART, the Pi side

### Takeaway

The documented, current recipe is EtherSLIP 11.8 (or DOSPPP's EPPPD) on the Compaq and `slattach` (or `pppd`) on the Pi, with mTCP on top; the mTCP manual has a full chapter with Raspberry Pi notes. I found no measured SLIP throughput for a 286 at 57600 or 115200: the ceiling is about 5.3 and 10.7 KB/s of TCP payload, and field reports on FIFO-less UARTs stop at 19200-38400.

### Cited Findings

**Drivers**

- [sourced] mTCP needs a class 1 (Ethernet-style) packet driver; over a serial port "The trick is to use a PPP or SLIP packet driver that emulates a class 1 packet driver (Ethernet)". Listed hardware includes "Generic 8250/16550 PC UART using SLIP or PPP to a Linux machine." — [mTCP manual 2026-10-10, pp. 11, 152](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)
- [sourced] The two drivers the manual names as working examples: PPP = DOSPPP 0.6 (`dosppp06.zip`), SLIP = EtherSLIP — [same, p. 152](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)
- [sourced] EtherSLIP 11.8 (released 2026-07-16 on GitHub; announced on the mTCP page 2026-04-13) fixes two bugs in the widely distributed Crynwr 11.7: a wrong destination MAC on received packets (which made mTCP NetDrive reject packets) and an ARP-reply pointer bug that "can corrupt memory and cause crashes" — [mbbrutman/EtherSLIP](https://github.com/mbbrutman/EtherSLIP), [releases](https://github.com/mbbrutman/EtherSLIP/releases), [mTCP home](http://www.brutman.com/mTCP/mTCP.html)
- [sourced] "Do not use the EtherSLIP version 11.7 packaged with the older Crynwr packet driver collection; it has a serious bug that can cause crashes." — [mTCP manual, p. 155](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)
- [sourced] EtherSLIP command line: `ethersl 0x60 4 0x3f8 9600` = packet interrupt 0x60, IRQ 4, port 3F8h (COM1), 9600 bps. COM2 is IRQ 3, port 2F8h — [same, p. 155](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)
- [sourced] DOSPPP command line: `EPPPD com1 9600 local`. "EPPPD is the PPP driver with Ethernet emulation." It writes an `IP-UP.BAT` for WATTCP programs — [same, pp. 153-154](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)
- [snippet] DOSPPP ships two drivers: PPPD emulates class 6 (SLIP), EPPPD emulates class 1 (Ethernet); it supports VJ header compression and CHAP. One user found MS-DOS Kermit's own TCP/IP worked with PPPD "out of the box" but not with EPPPD — [comp.protocols.kermit.misc thread](https://groups.google.com/g/comp.protocols.kermit.misc/c/_E4WZ_7jVm8/m/1ElNl4-8ZKMJ)
- [snippet] SLIPPER.EXE (plain SLIP) and CSLIPPER.EXE (compressed SLIP) are Peter Tattam's drivers and can emulate class 1; SLIP8250 is the older, simpler Crynwr driver (`slip8250 0x60`), class 6 — [lynx-dev list, 1997](https://lists.nongnu.org/archive/html/lynx-dev/1997-09/msg00178.html), [Dendarii DOS apps FAQ](http://www.dendarii.co.uk/FAQs/dos-apps.html)
- [sourced] Crynwr's collection and the packet driver specification are still hosted — [crynwr.com/drivers](http://crynwr.com/drivers/), linked from [mTCP home](http://www.brutman.com/mTCP/mTCP.html)

**mTCP configuration over SLIP or PPP**

- [sourced] Set `SET MTCPSLIP=true` (any value; used for both PPP and SLIP); use static IPADDR, NETMASK 255.255.255.255 and GATEWAY (the Pi's end); DHCP cannot be used; MTU 576 recommended and must match the Pi side — [mTCP manual, pp. 152, 156](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)
- [sourced] "You should verify that the link works using terminal emulation software before you start configuring PPP or SLIP" — [same, p. 152](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)

**Pi side**

- [sourced] SLIP: `slattach -p slip -L -s 9600 /dev/ttyUSB0`, then `ifconfig sl0 192.168.2.91 pointopoint 192.168.2.92 mtu 576 up` (or `ip addr add 192.168.2.91 peer 192.168.2.92 dev sl0; ip link set sl0 mtu 576; ip link set sl0 up`). `-L` disables modem-control lines for a null-modem cable — [mTCP manual, pp. 154-155](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)
- [snippet] slattach's default protocol is `cslip`, so `-p slip` must be given for a plain-SLIP driver; it supports standard rates up to 115200 — [slattach(8)](https://linux.die.net/man/8/slattach)
- [sourced] PPP: `sudo pppd ttyUSB0 9600 local lock passive proxyarp defaultroute noauth mtu 576 192.168.2.91:192.168.2.92`; add `nocrtscts` if hardware flow control is not wired — [mTCP manual, p. 153](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)
- [sourced] To reach beyond the Pi: SLIP needs proxy ARP by hand (`sudo arp -Ds 192.168.2.92 wlan0 pub`; pppd's `proxyarp` does it for PPP), IP forwarding (`echo 1 | sudo tee /proc/sys/net/ipv4/ip_forward`), and "Raspberry Pi WiFi users: Enable promiscuous mode on wlan0" (`sudo /sbin/ip link set wlan0 promisc on`); NAT on the Pi is the alternative — [same, pp. 157-158](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)
- [sourced] Any `getty` login on that serial port must be disabled first: "The serial port must be dedicated to the PPP or SLIP connection." — [same, p. 153](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)

**Speed and reliability evidence**

- [sourced] Reference timing: "at 9600 bps you get about one byte per millisecond"; a 32-byte ping over PPP at 9600 takes about 150 ms on a 386 — [mTCP manual, p. 156](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)
- [snippet] "SLIP at 115,200 is good for at most 10KB/sec", and "somebody with a 286 Toshiba laptop was able to make it work at 115,200" (anecdote, no figures) — [VOGONS NetDrive thread](https://www.vogons.org/viewtopic.php?p=1235879)
- [sourced] 2026 field report, IBM 5155 (8088, 4.77 MHz, FIFO-less UART) to a Raspberry Pi 5 over USB-RS232 with ETHERSL.COM and mTCP: failed at 115200 with a Prolific adapter; worked at 19200, then at 38400 on a multi-I/O card for terminal, YMODEM and SLIP; a different machine's on-board port topped out at 9600. The working Pi side used `slattach -h` (hardware handshake) plus `stty -F /dev/ttyUSB0 crtscts <speed>`. No throughput figure was given — [classic-computing.de thread, Mar-Apr 2026](https://forum.classic-computing.de/forum/index.php?thread/39299-funktionierende-slip-config-zwischen-pc-xt-8088-4-77mhz-und-raspberry-pi5-via-us/)
- [sourced] Same thread, advice from another member: an 8250 without FIFO must service every byte in the interrupt routine; replace it with a pin-compatible 16550 if possible; RTS/CTS helps less than expected with FTDI adapters because the chip still sends 2-3 buffered bytes after CTS drops; PPP is a fallback because it can escape XON/XOFF — [same thread](https://forum.classic-computing.de/forum/index.php?thread/39299-funktionierende-slip-config-zwischen-pc-xt-8088-4-77mhz-und-raspberry-pi5-via-us/)
- [snippet] Why a FIFO-less UART drops data: with a one-byte receive buffer "there is a genuine risk that a received byte will be overwritten if interrupt service delays occur" — [Wikipedia: 16550 UART](https://en.wikipedia.org/wiki/16550_UART)
- [not re-read] Kermit's own guidance for its terminal emulator on AT-class machines is "generally 19200, perhaps 38400" (carried over from the earlier doc's source) — [mskerm.bwr](https://ftp.math.utah.edu/public_html/pub/ibmpc/kermit/mskerm.bwr)

### Inferences

- [estimate] Ceilings by arithmetic (8N1 = 10 bits per byte; MTU 576 leaves 536 bytes of TCP payload per 576 + framing): 9600 = 0.96 KB/s raw, about 0.89 KB/s payload; 38400 = 3.84 raw, about 3.6; 57600 = 5.76 raw, about 5.3; 115200 = 11.52 raw, about 10.7. Acknowledgements and SLIP escape bytes take a little more. Real file transfers to a floppy or old hard disk will be lower.
- [estimate] At 115200 a byte arrives every 87 microseconds. A 12 MHz 286 can service that in a tight program that owns the machine, but any stretch with interrupts off longer than 87 microseconds (BIOS disk I/O, BIOS screen scrolling, the timer tick chain) loses a byte on a 16450. With SLIP a lost byte costs a whole packet and a TCP retransmit, so the failure mode is stalls and slow transfers, not corrupt files. 57600 doubles the margin; 38400 is the highest speed with field evidence on FIFO-less hardware.
- [estimate] Practical plan: bring SLIP up at 9600 exactly as documented, then step to 19200, 38400, 57600, 115200 while running mTCP `SPDTEST` or an FTP `get` to NUL and watching for retransmits. Wire RTS/CTS in the null-modem cable. On the Pi 3 B+ prefer its on-board PL011 UART through a MAX3232 level shifter over a USB adapter, because the adapter's buffering is what defeats hardware flow control.
- [estimate] PPP versus SLIP here: PPP (EPPPD) adds per-frame checksums and negotiates addresses, pppd handles proxy ARP itself, and VJ compression shrinks the 40-byte TCP/IP header on interactive traffic; SLIP (EtherSLIP) is smaller and simpler. On a clean 2 m null-modem cable both are fine; EtherSLIP 11.8 is the one actively maintained in 2026.
- [estimate] One serial port means SLIP and the Kermit terminal session take turns. The swap could be scripted on both ends (stop the bridge's getty/terminal, start `slattach`; on DOS unload Kermit, load `ethersl`).
- [estimate] The cable is the bottleneck for everything in question 5 and 6: at 38400 a 20 KB image takes about 6 seconds, at 115200 about 2.
- **Earlier-doc check.** "EtherSLIP plus mTCP turns the cable into a network link at about 5-7 KB/s": the mechanism is confirmed; the figure has no source I could find and corresponds to a clean 57600-115200 link. "A 12 MHz 286 without a FIFO has done 57600 with ZMODEM; 115200 gave errors": I found no source for this either; the nearest evidence is the 19200-38400 XT report and the 115200 Toshiba 286 anecdote above.

### Gaps

- No measured mTCP-over-SLIP throughput on any 286 at 57600 or 115200 was found.
- EtherSLIP's own documentation of maximum baud rate, FIFO handling and hardware handshake options was not found on its GitHub page; the Crynwr source would settle it.
- Memory footprint of EtherSLIP and EPPPD was not found (packet drivers in general: "5 to 30 KB" — [mTCP manual](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)).
- CSLIPPER's and SLIP8250's requirements and behaviour at high speed were not verified from primary documentation.
- Two pages that might hold real numbers could not be opened: Adam Pachulski's "Connecting a 286 DOS PC to the Internet Through a Serial Connection ... in 2019" ([Medium](https://medium.com/swlh/connecting-a-286-dos-pc-to-the-internet-through-a-serial-connection-in-2019-b93a422ff094), linked from the mTCP page, HTTP 403) and ToughDev's 2025 Pocket 386 SLIP article ([toughdev.com](https://www.toughdev.com/content/2025/08/internet-access-from-pocket-386-using-wemos-d1-esp8266-serial-wifi-adapter/), certificate error).

---

## 5. mTCP: current version, requirements, the apps that matter, and the Sixel claim

### Takeaway

mTCP 2026-10-10 is current, runs on an 8088 with DOS 2.1+ and 128-384 KB free, and fits this machine comfortably. The Sixel claim is true: black-and-white Sixel in Telnet shipped on 2026-10-10 (it first appeared in January 2025 and was pulled four days later). NetDrive got a large speed-up in the same release and works over EtherSLIP 11.8, but under DOS 3.1 its images are limited to 32 MB.

### Cited Findings

- [sourced] "Current version: October 10th, 2026". "This version has some bug fixes, adds black and white Sixel graphics to Telnet, makes Ping more accurate, and has major performance improvements for NetDrive. The HTTP server source code is also now included." Since 2026-06-29 the official source is also at github.com/mbbrutman/mTCP. GPLv3 — [mTCP home](http://www.brutman.com/mTCP/mTCP.html)
- [sourced] Requirements: "An IBM PC compatible with an 8088 or better CPU"; "96KB to 384KB of system memory depending on the application" (the manual says 128-384 KB); "DOS 2.1 or newer"; a packet driver that is Ethernet or emulates it, including "Serial ports using SLIP, Compressed SLIP, or PPP connections" — [mTCP home](http://www.brutman.com/mTCP/mTCP.html), [manual p. 11](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)
- [sourced] Programs: DHCP, FTP, FTPSRV, HTGET, HTTPSERV, IRCJR, NC (netcat), NetDrive, PING, PKTTOOL, SNTP, TELNET; SPDTEST for benchmarking — [mTCP home](http://www.brutman.com/mTCP/mTCP.html), [performance notes](http://brutmanlabs.org/mTCP/mTCP_Performance.html)
- [sourced] There is no TSR version; each program links the stack, and mTCP only answers the network while one of its programs is running — [mTCP home](http://www.brutman.com/mTCP/mTCP.html), [manual p. 156](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf)

**Telnet and Sixel**

- [sourced] Release notes: "Telnet has better compatibility with Telnet BBSes and now can display black and white SIXEL graphics." — [2026-10-10 release notes](http://brutmanlabs.org/mTCP/mTCP_2026-10-10_Release_Notes.html)
- [sourced] Details: "Only black and white Sixel graphics are supported ... The maximum horizontal resolution is 640 pixels. There is no maximum vertical resolution, as the display will scroll the image"; prepare images with `convert` and `img2sixel -e`; "The 640x200 graphics mode has a strange aspect ratio; the dots are nearly 2x taller than they are wide." Telnet also shows CompuServe RLE graphics, has Xmodem/Ymodem built in, UTF-8, and CGA/EGA/VGA/MDA text support. Test server: `telnet brutman.com 8086` — [manual p. 140](http://www.brutman.com/mTCP/download/mTCP_2026-10-10.pdf), [Telnet page](http://brutmanlabs.org/mTCP/mTCP_Telnet.html)
- [sourced] History: the 2025-01-10 release announced black-and-white Sixel "in less than 1KB of code"; on 2025-01-14 the author found it "blanked his screen during a vim session", re-issued the binaries with Sixel disabled, and it stayed out until 2026-10-10 — [mTCP mailing list](https://groups.google.com/g/mtcp/c/as0c5Ta94UQ)
- [sourced] A fork adds colour Sixel, mouse and printer support, based on the 2022-07-01 source — [jhpyle/mTCP](https://github.com/jhpyle/mTCP), described on the [Telnet page](http://brutmanlabs.org/mTCP/mTCP_Telnet.html)

**NetDrive**

- [sourced] "A DOS device driver that allows you to access a remote disk image hosted by another machine as though it was a local device with an assigned drive letter." Works "with all versions of DOS starting with DOS 2.0"; driver "uses less than 9KB of RAM" plus the packet driver; UDP-based; several drives at once; checkpoint/undo; "DOS versions with FAT16B support can use remote images up to 2GB in size. (FAT12 and FAT16 are limited to 32MB images.)" — [NetDrive page](http://brutmanlabs.org/mTCP/mTCP_NetDrive.html)
- [sourced] Server binaries are provided for "Linux ARM (32 bit and 64 bit)", so it runs on the Pi; the server is written in Go — [mTCP home](http://www.brutman.com/mTCP/mTCP.html)
- [sourced] 2026-10-10 changes: read-ahead and "large writes"; "a fast 386 class machine saw read speeds improve by 2.5x on a local network and 20x when connected to a remote server"; the pass-through packet driver now lets non-mTCP programs (NCSA Telnet, Trumpet Winsock) share the link while a drive is mounted — [release notes](http://brutmanlabs.org/mTCP/mTCP_2026-10-10_Release_Notes.html)
- [sourced] NetDrive over SLIP specifically needs the 11.8 EtherSLIP, because 11.7's MAC bug made NetDrive reject packets — [EtherSLIP README](https://github.com/mbbrutman/EtherSLIP)

### Inferences

- [estimate] Useful here, in order: **FTP** and **HTGET** (pull programs and data from the Pi without Kermit transfers), **NetDrive** (the Pi becomes a hard disk: a way round the missing or small hard disk and the 1.2 MB floppy), **Telnet** (a second terminal with Sixel and RLE pictures and Ymodem), **IRCjr**, **NC** (a raw TCP pipe to custom Pi services), **SNTP** (set the clock).
- [estimate] NetDrive speed is the link speed: a 300 KB program loads in roughly 30 seconds at 115200 and 85 seconds at 38400. Fine for tools, poor for Doom's WAD. Over an NE2000 or PicoMEM it would feel like a slow hard disk.
- [estimate] MS-DOS 3.1 has no FAT16B, so each NetDrive image is capped at 32 MB; mount several if needed.
- [estimate] mTCP Telnet's Sixel is drawn in CGA 640x200 (the manual's aspect-ratio note refers to that mode), not the plasma's 640x400. MS-DOS Kermit's Sixel, already in use, is the comparison point; which is faster on this machine is untested.
- **Earlier-doc check.** "telnet (reportedly with sixel images since October 2026)": confirmed, black and white only, 640 pixels wide. "NetDrive, which mounts a disk image served by the Pi as a Compaq drive letter": confirmed.

### Gaps

- Per-program memory needs are given only as a range; the manual has no table.
- No NetDrive throughput over SLIP was found.
- Whether mTCP Telnet can be made to use the 640x400 mode is not documented.

---

## 6. MicroWeb, HTTPS proxies for the Pi, and other browsers for a 286 with CGA

### Takeaway

MicroWeb 2.1 (March 2026) runs on an 8088 with CGA and has a 640x400 mode that uses BIOS mode 40h, labelled "Olivetti M24" in the program; the 0.53 release notes say that mode is the one the Compaq Portable III uses. It renders GIF only and has no TLS, so the Pi must run a proxy; WRP is the notable option because it turns any modern page into a clickable GIF, which also makes it the nearest thing to a remote-display client.

### Cited Findings

**MicroWeb**

- [sourced] Releases: v2.1 on 2026-03-12 (XMS support, simple file downloads, better memory use, fixes); v2.0 on 2024-04-17 (more video modes, GIF images, PNG/JPEG dimensions only, tables and forms, EMS); v0.53 on 2023-07-08 — [releases](https://github.com/jhhoward/MicroWeb/releases) (dates from the GitHub API)
- [sourced] v0.53 note: "Added support for 640x400 mode used by Olivetti M24, AT&T PC 6300, Compaq Portable II/III, and Toshiba T3100" — [releases](https://github.com/jhhoward/MicroWeb/releases)
- [sourced] Requirements: "Intel 8088 or compatible CPU", "CGA, EGA, VGA or Hercules compatible graphics card", "640K RAM is desirable but can run with less", "Extra memory via XMS or EMS can be used if available and is recommended for loading heavier web pages and images", a packet driver ("it is possible to use your machine's serial port with the EtherSLIP driver"), mouse optional. It uses the mTCP library — [README](https://github.com/jhhoward/MicroWeb)
- [sourced] Video modes listed include "640x200 monochrome (CGA)", "640x400 monochrome (Olivetti M24)" and "640x400 monochrome (Toshiba T3100)". There is no entry named for Compaq — [README](https://github.com/jhhoward/MicroWeb)
- [derived] In the source the Olivetti entry is BIOS mode 0x40, 1 bit per pixel, with four interleaved line banks at B800, BA00, BC00 and BE00; the Toshiba entry is mode 0x74 — [src/VidModes.cpp](https://github.com/jhhoward/MicroWeb/blob/master/src/VidModes.cpp)
- [sourced] Limits: "HTTP only", "No CSS or Javascript", "Only GIF images are rendered, although PNG and JPEG dimensions are loaded for layout purposes", "Large or complex pages may be truncated if there is not enough RAM available". Options: `-noimages`, `-noems`, `-noxms`, `-useswap` ("Experimental disk swapping mode to increase available memory") — [README](https://github.com/jhhoward/MicroWeb)
- [sourced] HTTPS: "TLS encryption is currently not supported"; use a proxy and `SET HTTP_PROXY=192.168.0.50:8000`, or the FrogFind service — [README](https://github.com/jhhoward/MicroWeb)
- [sourced] Brutman redistributes "MicroWeb 2.1 ... recompiled to use the newest mTCP version" — [mTCP home](http://www.brutman.com/mTCP/mTCP.html)
- [derived] MicroWeb parses the `ismap` attribute on images (`imageNode->isMap = true`), the mechanism image-map proxies rely on — [src/Tags.cpp](https://github.com/jhhoward/MicroWeb/blob/master/src/Tags.cpp)
- [sourced] The Compaq plasma mode is "functionally very similar to the AT&T 6300 / Olivetti in terms of the 640x400 graphics mode" (86Box contributor, Dec 2024) — [86Box issue 5011](https://github.com/86Box/86Box/issues/5011). Compaq's manual tells users to pick AT&T 6300 640x400 drivers in many programs — [Operations Guide, Appendix C](https://archive.org/details/compaq-portable-3-operations-user-manual)

**Proxies that can run on the Pi**

- [sourced] retro-proxy (Node.js; install path given for "Debian, Raspberry Pi, or Ubuntu"): "bypass modern https" and "attempts to modify modern web pages to make them usable on vintage web browsers"; per-site bypass list in `allowed.txt`. Its README does not mention image conversion — [DrKylstein/retro-proxy](https://github.com/DrKylstein/retro-proxy)
- [sourced] WebOne (.NET 8, Windows/Linux/macOS, an ARMv6 build script is included, default port 8080): strips HTTPS, converts HTTP 1.1 to 1.0, re-encodes character sets, patches content, and converts or recompresses images "on the fly" through ImageMagick — [atauenis/webone](https://github.com/atauenis/webone)
- [sourced] WRP, Web Rendering Proxy (Go plus headless Chrome/Chromium): renders the page server-side as "a GIF/PNG/JPG image with clickable imagemap"; default image type GIF; geometry flag `-g` width x height x colours (default 1152x600x216; height 0 gives one tall scrolling image); clients need only forms and ISMAP ("as old as NCSA Mosaic 2.0"); also has a "simple html aka reader aka text mode". Raspberry Pi is supported through arm64 containers; there is no 32-bit ARM image — [tenox7/wrp](https://github.com/tenox7/wrp)
- [sourced] Browservice (server-side Chromium) is not usable: "The client browser runs a JavaScript application that requests and shows the images", output is PNG or JPEG, and the project is now unmaintained — [ttalvitie/browservice](https://github.com/ttalvitie/browservice)
- [snippet] MacProxy (Python/Flask) translates HTTPS to HTTP and strips scripts and styles; FrogFind is a hosted readability-style service that is "much more aggressive with the downsizing of contents" — [PiSCSI wiki: Vintage Web Proxy](https://github.com/akuker/RASCSI/wiki/Vintage-Web-Proxy), [TinkerDifferent thread](https://tinkerdifferent.com/threads/http-proxy-and-transcoder-for-vintage-browsers.275)
- [sourced] MicroWeb's own release notes report that 68k.news and FrogFind work well — [releases](https://github.com/jhhoward/MicroWeb/releases)
- [snippet] Any such proxy removes transport security and should stay on a private network — [zenwheel/legacyproxy](https://github.com/zenwheel/legacyproxy)

**Other browsers and graphical net clients**

- [snippet] DOSLynx: text-mode browser; "Graphics capability: Optional. Mouse: Optional"; networking needs a class 1 packet driver; its README says versions (of DOS) below 3.0 will not work properly — [DosLynx README](https://pieter.com/assets/c/LYNX/README.HTM)
- [snippet] Arachne: the distributor's listing requires "80386, 80387 FPU (or 80486+ CPU), CGA/EGA video (SVGA/VESA recommended)" — [bttr-software list](https://bttr-software.de/freesoft/comm2.htm). Forum users report older 8086/286 builds ("1.97;GPL.286") running on a 286/12 with 8 MB — [VOGONS](https://vogons.org/viewtopic.php?p=1321084)
- [snippet] Minuet is listed as "An all-in-one Internet access package for MSDOS. Includes both text-mode and graphics-mode display" with no stated hardware requirements — [bttr-software list](https://bttr-software.de/freesoft/comm2.htm)

### Inferences

- [estimate] On the Portable III, start MicroWeb and choose "640x400 monochrome (Olivetti M24)". It should work because the mode is set through the BIOS (mode 40h) and the memory layout matches what Compaq describes as AT&T-compatible. I found no first-hand report of MicroWeb on a real Portable III, so test it; "640x200 monochrome (CGA)" is the fallback.
- [estimate] With 640 KB and no EMS or XMS, expect truncated pages and few images. `-noimages` and `-useswap` are the levers; a PicoMEM's EMS would lift this limit.
- [estimate] Best proxy fits for this client: (1) a local readability-style or MacProxy/retro-proxy filter for text pages, since MicroWeb ignores CSS and scripts anyway; (2) WebOne if images are wanted, configured to convert PNG/JPEG/WebP to small 1-bit GIFs (possible in principle through its ImageMagick hook; the exact rule is not documented in the README I read); (3) WRP in GIF mode at about 600 pixels wide for sites that only work in a real browser. Untested with MicroWeb: MicroWeb must also submit the click coordinates and decode a large GIF in its limited memory.
- [estimate] WRP needs a 64-bit OS on the Pi 3 B+ (the chip is 64-bit capable) and headless Chromium in 1 GB of RAM, which is tight but workable for one page at a time.
- [estimate] A page screenshot as a 1-bit 640x400 GIF is roughly 10-30 KB, so 1-3 seconds at 115200 and 3-8 seconds at 38400.
- [estimate] Arachne is not a realistic option at 640 KB on a CGA-class display; DOSLynx is, for text.
- **Earlier-doc check.** "MicroWeb ... added a 640x400 mode for the Compaq Portable II/III, shows GIF images, and needs a proxy on the Pi for HTTPS sites": confirmed, with the correction that the menu entry is named for the Olivetti M24.

### Gaps

- No confirmed report of MicroWeb running in 640x400 on a real Compaq Portable III.
- I could not open Ralf Brown's Interrupt List or VGADOC to confirm independently that the Compaq BIOS implements mode 40h; the support is the MicroWeb release note plus Compaq's AT&T-driver guidance.
- MicroWeb's minimum DOS version is not stated.
- retro-proxy's and WebOne's exact image-conversion options were not verified beyond their READMEs.
- Minuet's and DOSLynx's memory requirements and behaviour on the plasma display were not verified.

---

## 7. Remote-display clients for DOS on a 286 with CGA or 640x400 mono

### Takeaway

I found no ready-made VNC, RDP or X client that works on this machine. The one real-mode VNC viewer is VGA-only alpha software from 2004, and the DOS X servers for 286s needed protected mode and extended memory. The workable remote-display routes are image-over-terminal (Sixel or RLE in mTCP Telnet, Sixel in Kermit), a page-as-GIF proxy (WRP) viewed in MicroWeb, or the custom frame client the earlier doc proposes.

### Cited Findings

- [sourced] VNC Viewer 8086: "PC compatible computer with a 8086 or higher processor", "512 KB RAM", uses WATTCP, "Only tested on a 286 with 1 MB of RAM". Display is "640x480x16 (grey levels) VGA"; "Full VGA/EGA/CGA support" is only a priority-1 roadmap item; only Hextile encoding is enabled; status alpha, last news May 2004 — [project page](https://vncviewer8086.sourceforge.net/). [snippet] Keyboard limited to ASCII keys, mouse to the left button; packaged for FreeDOS as vncview 3.3.7a — [FreeDOS package list](https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/repositories/1.3/pkg-html/vncview.html)
- [snippet] X servers for DOS on a 286 existed but not in real mode: PC DECwindows ran "on a 286 system on top of a Rational Systems DOS extender", and a poster notes "there was no thought of trying to fit any sort of implementation in a real mode 8088 system"; DESQview/X had a 286 edition (DVX286) — [cctalk thread, 2016](https://classiccmp.org/pipermail/cctalk/2016-August/026612.html); PC-Xview is described as "a DOS-based X-Windows terminal emulator for 286/386 PCs" — [EDM2](https://www.edm2.com/index.php/X_Window_System)
- [sourced] Browservice needs client-side JavaScript; WRP needs only forms and ISMAP and serves GIF — [Browservice](https://github.com/ttalvitie/browservice), [WRP](https://github.com/tenox7/wrp)
- [sourced] mTCP Telnet shows black-and-white Sixel up to 640 pixels wide, scrolling vertically, and CompuServe RLE images — [mTCP Telnet](http://brutmanlabs.org/mTCP/mTCP_Telnet.html)

### Inferences

- [estimate] VNC Viewer 8086 is unusable here: the plasma controller is a CGA superset with no VGA modes, and the software has had no release since 2004.
- [estimate] A DOS-extender X server needs extended memory. This machine has exactly 640 KB, so none of them can load, apart from the question of display drivers for a CGA-class screen. Unusable.
- [estimate] No RDP client for a real-mode 286 turned up; RDP's bitmap codecs and encryption make one unlikely. I did not find evidence either way for the old 16-bit Citrix ICA DOS client.
- [estimate] The gap is real, which supports the earlier doc's plan to write a small custom frame client. A simpler stepping stone exists once SLIP works: mTCP's `NC` or a tiny mTCP-library program can receive frames over TCP from the Pi, which removes the need to handle the UART, framing and retransmission by hand (at the cost of TCP/IP overhead on the 286).
- [estimate] Frame-rate ceilings are set by the cable (question 4), not by the choice of client.

### Gaps

- No evidence of any maintained thin-client program for 8086/286 with CGA.
- DESQview/X-286's and PC-Xview's exact memory and display requirements were not found in a primary document.
- I did not search for Tektronix 4010/4014 vector clients beyond what Kermit already offers.

---

## 8. Windows 3.0 in real mode, GEM and similar on the AT&T/Olivetti 640x400 driver

### Takeaway

GEM and Windows 1.x on the AT&T 6300 640x400 driver are Compaq-documented and should work. Windows 3.0 is limited to real mode on 640 KB; its dedicated "Compaq Portable Plasma" driver has one report of failing on a real Portable III (286), with CGA as the fallback. None of these environments adds networking or program capability that DOS programs do not already give.

### Cited Findings

- [sourced] Compaq's own installation examples for the plasma display: Windows 1.03, "Select option 7 during SETUP: AT&T PC 6300 or 6300+ display adapter (for 640 x 400 graphics mode)"; GEM Desktop, "select the AT&T Monochrome Card (640 x 400) display driver"; Lotus 1-2-3, "AT&T 640 x 400 single color driver or the AT&T 640 x 400 50 line mode driver"; Framework II, "AT&T PC 6300 (Olivetti M24) ... will install in 640 x 400 graphics mode"; Word 3.1, VersaCAD and Ventura Publisher likewise. AutoCAD, Chart-Master and the Harvard titles "do not support the 640 x 400 mode" and install as CGA — [Operations Guide, Appendix C](https://archive.org/details/compaq-portable-3-operations-user-manual)
- [sourced] Wikipedia says Windows 2.11 included a Compaq Portable display driver for 640x400 — [Wikipedia: Compaq Portable III](https://en.wikipedia.org/wiki/Compaq_Portable_III)
- [sourced] Windows 3.0 modes: real mode "works with only 640 KB", official minimum CPU "an 8 MHz turbo 8086", and it "primarily existed as a way to run Windows 2.x applications"; standard mode needs "an 80286 processor with at least 1 MB of memory"; 386 enhanced mode needs a 386 and 2 MB. On some Compaqs with a memory hole, Windows "could not work on them except in real mode". Displays: EGA/MCGA/VGA recommended, "works with CGA and Hercules" — [Wikipedia: Windows 3.0](https://en.wikipedia.org/wiki/Windows_3.0)
- [sourced] Real-hardware report: on a Portable III (286), "all my Windows 3.0/3.1 attempts in this mode (with Plasma.drv) fail to start"; the owner believed it "seems to work only from the Portable 386 on" and stayed with CGA (Kjell, 23 Mar 2017) — [DOSReloaded thread](https://dosreloaded.de/forum/thread/489-compaq-portable-iii-restauration-upgrades/)
- [sourced] Emulator report: "86Box currently works fine with Windows 3.x with the auto-detected driver for that", tested on the emulated Portable III/386 (`machine = portableiii386`) — [86Box issue 5011](https://github.com/86Box/86Box/issues/5011)
- [snippet] A forum post says the Compaq Plasma driver for Windows 3.0/3.1 also works on an Olivetti M24, and that the driver was left off the Windows for Workgroups 3.11 disks — [bannister.org forum](https://forums.bannister.org/ubbthreads.php?ubb=printthread&Board=1&main=8753&type=thread)
- [snippet] Windows 3.0 Setup also offers an "Olivetti/AT&T Monochrome" display choice; on a Toshiba T3100 Setup auto-selected it and the user had to switch to CGA — [WinWorld forum](https://forum.winworldpc.com/discussion/comment/160996)
- [sourced] A small utility recreates parts of Compaq's `MODE.COM` (video CGA/MDA, CPU speed, internal/external monitor) for the Portable III and 386, and notes that Compaq's own `MODE.COM` is tied to its exact DOS version — [indrekis/compaq_portable_III_conf](https://github.com/indrekis/compaq_portable_III_conf)

### Inferences

- [estimate] GEM and Windows 1.x/2.x at 640x400 are low-risk: Compaq documented the driver choice. They give a crisp desktop and a few period applications (GEM Draw, Paint, Write; Windows Write, Paint), nothing network-related.
- [estimate] Windows 3.0 on this machine means real mode only (no extended memory at 640 KB): one conventional-memory heap shared by Windows and its applications, no Winsock stack worth having (Trumpet Winsock and browsers of that era want Windows 3.1 in standard or enhanced mode with megabytes of RAM), and slow drawing through BIOS-speed drivers. Try the display drivers in this order: Compaq Portable Plasma, Olivetti/AT&T monochrome, CGA. Treat it as a curiosity.
- [estimate] The PLASMA.DRV failure on a 286 may be a 386-specific driver build or a setup issue; one report is not proof. The Olivetti/AT&T driver is the likelier route to 640x400 because it matches Compaq's Windows 1.03 advice.
- [estimate] Adding RAM would unlock Windows 3.0/3.1 standard mode, but that needs Compaq memory modules or a PicoMEM in the expansion unit; even then a 12 MHz 286 on a 1-bit display is poor value compared with native DOS programs.
- **Earlier-doc check.** "Compaq's manual says to use the AT&T/Olivetti 640x400 drivers in Windows and GEM": confirmed for Windows 1.03 and GEM Desktop. The manual predates Windows 3.0 and says nothing about it.

### Gaps

- I could not read the Windows 3.0 `SETUP.INF` display list to confirm the exact driver names shipped; the names above come from forum posts.
- No first-hand report of Windows 3.0 with the Olivetti/AT&T driver on a real Portable III (286).
- No first-hand 2018-2026 report of GEM on a Portable III; the evidence is Compaq's 1987-88 manual.
- VOGONS threads on these topics could not be opened from this environment.
