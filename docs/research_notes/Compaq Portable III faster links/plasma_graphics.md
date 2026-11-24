# Compaq Portable III plasma graphics and 1-bit video techniques (researched 2026-10-13)

How to read these notes:

- **Sourced** facts carry a link. Source code was read directly from the repositories on 2026-10-13 (default branches) and is quoted exactly.
- **Emulator model** means the fact comes from emulator source code (86Box or MAME). It shows what the emulator authors believe the hardware does. It is not a measurement on a real Portable III.
- **Estimate** and **Inference** are mine and are labelled.
- "Search snippet" means the page could not be opened from this environment (Vogons blocks direct fetches) and the fact comes from the search engine's excerpt only.
- Everything is about the Portable III (286) unless a line says Portable 386, AT&T 6300, Olivetti M24 or Toshiba.

## 1. The 640x400 mode: BIOS mode number, entering and leaving, I/O ports, memory layout, and how it differs from the AT&T 6300 / Olivetti M24

### Takeaway
The mode is BIOS mode 40h, and on the Compaq the hardware switch is bit 0 of port 23C6h (not the M24's port 3DEh). Video memory is 32 KB at B800:0000 in four interleaved 8 KB banks: line y lives in bank (y mod 4) at byte offset (y div 4) x 80. That layout is the same as the AT&T 6300 / Olivetti M24, so the earlier notes were right on the layout and the port, and wrong only in calling the mode "unique to Compaq".

### Cited Findings

**Mode number**

- Ralf Brown's Interrupt List (INT 10h AH=00h mode table) lists mode 40h three times with identical parameters, one row per machine family. The rows, with the file's tab spacing collapsed: `= G  80x25  8x16  640x400  2  1  B800 AT&T 6300, AT&T VDC600`, `= G  80x25  8x16  640x400  2  1  B800 Olivetti Quaderno`, `= G  80x25  8x16  640x400  2  1  B800 Compaq Portable`. So: graphics, 640x400, 2 colours, 1 page, segment B800h. — [RBIL INTERRUP.A, release 61](https://github.com/cirosantilli/ralf-brown-interrupt-list/blob/master/inter61a/INTERRUP.A)
- VGADOC's Compaq file lists, in its Compaq BIOS mode table: `40h  G   640  400     2       Compaq Portable only`. "Only" here means "of the Compaq products", because the table is Compaq's own mode list. — [VGADOC COMPAQ.TXT](https://pdos.csail.mit.edu/6.828/2018/readings/hardware/vgadoc/COMPAQ.TXT)
- VGADOC documents port 23C6h only as a bare heading (`23C6h (R/W):` with no bit description). It does not describe the 400-line bit. The bit description comes from John Elliott, below. — [VGADOC COMPAQ.TXT](https://pdos.csail.mit.edu/6.828/2018/readings/hardware/vgadoc/COMPAQ.TXT)
- RBIL also lists mode 48h (`G 80x50 8x8 640x400 2 B800`) for the AT&T 6300 and Olivetti Quaderno, with no Compaq row. — [RBIL INTERRUP.A](https://github.com/cirosantilli/ralf-brown-interrupt-list/blob/master/inter61a/INTERRUP.A)

**The Compaq I/O ports (John Elliott, from his own Portable III, BIOS revision K dated 29 January 1987)**

- `23C6h [r/w]  Bit 0: Set for 400-line graphics mode. Reset for 200-line graphics mode or for text.` — [John Elliott, Compaq Portable III](https://www.seasip.info/VintagePC/compaq3.html)
- Same port, `Bit 3: Set to map the character generator RAM into memory where the video RAM would normally be (at B8000 or B0000). The main font is at offset 0, the alternate font at offset 1000h.` Setting this bit by accident replaces the frame buffer with font RAM. — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)
- Same port, bit 4 is "Active intensity bit interpretation" and bits 5-7 choose how the high-intensity text attribute is shown (see section 2). A program that pokes bit 0 must keep the other bits. — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)
- `13C6h [r/w]`: bits 0-2 master mode (0=CGA, 1=EGA, 3=MDA), bit 3 active monitor (set = internal plasma, reset = external), bit 6 reads 0 when the Compaq extended video functions (INT 10h AX=BFxxh) exist. — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)
- `1BC6h [read]`: bits 4-7 internal monitor type, `4=> 640x400 flat panel`. `17C6h [read]` returned 0E6h on his machine. `27C6h [r/w]`: bits 0-5 plasma timeout in minutes. — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)
- The page does not mention port 3DEh anywhere. — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)

**The memory layout, from three independent code bases**

- 86Box, Compaq plasma renderer (emulator model). In hi-res graphics the address of each displayed line is:
  ```c
  /* 640x400 mode */
  if (self->port_23c6 & 0x01) /* 640*400 */ {
      addr = ((self->cga.displine) & 1) * 0x2000 + ((self->cga.displine >> 1) & 1) * 0x4000 + (self->cga.displine >> 2) * 80 + ((memaddr & ~1) << 1);
  } else {
      addr = ((self->cga.displine >> 1) & 1) * 0x2000 + (self->cga.displine >> 2) * 80 + ((memaddr & ~1) << 1);
  }
  ```
  So in 640x400, panel line 0 is at offset 0000h, line 1 at 2000h, line 2 at 4000h, line 3 at 6000h, line 4 at 0050h, and so on. In 640x200 (mode 6) each CGA line is shown on two panel lines, with the usual two CGA banks. — [86Box src/video/vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- 86Box maps 32 KB of video RAM at B8000h for this card: `mem_mapping_add(&self->cga.mapping, 0xb8000, 0x08000, ...)` and reads it as `self->cga.vram[addr & 0x7fff]`. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- 86Box decides between the plasma renderer and plain CGA with the comment `/* graphic mode and not mode 40h */` on `if (!self->internal_monitor && !(self->port_23c6 & 0x01))`, and its 640x400 path also requires `self->cga.cgamode & CGA_MODE_FLAG_HIGHRES_GRAPHICS` (mode-control register 3D8h in hi-res graphics, as in mode 6). — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- MicroWeb (a real DOS program) uses BIOS mode 40h and the same four banks. Mode table row: `{ "640x400 monochrome (Olivetti M24)", 0x40, 640, 400, DrawSurface::Format_1BPP, 100, 100, DataPack::Default, false, 0xb800, 0xba00, 0xbc00, 0xbe00 },`. — [MicroWeb src/VidModes.cpp](https://github.com/jhhoward/MicroWeb/blob/master/src/VidModes.cpp)
- MicroWeb's line table code:
  ```cpp
  // 4 page interlaced memory layout
  int offset = 0;
  for (int y = 0; y < screenHeight; y += 4)
  {
      drawSurface->lines[y] = (uint8_t*)MK_FP(videoMode->vramPage1, offset);
      drawSurface->lines[y + 1] = (uint8_t*)MK_FP(videoMode->vramPage2, offset);
      drawSurface->lines[y + 2] = (uint8_t*)MK_FP(videoMode->vramPage3, offset);
      drawSurface->lines[y + 3] = (uint8_t*)MK_FP(videoMode->vramPage4, offset);
      offset += screenPitch;
  }
  ```
  with `screenPitch = screenWidth / 8` (80 bytes). — [MicroWeb src/DOS/BIOSVid.cpp](https://github.com/jhhoward/MicroWeb/blob/master/src/DOS/BIOSVid.cpp)
- MicroWeb enters the mode with plain INT 10h AH=00h (`inreg.h.ah = 0; inreg.h.al = (unsigned char)screenMode; int86(0x10, &inreg, &outreg); return GetScreenMode() == screenMode;`) and leaves by restoring the mode it found at start-up. It writes no Compaq or Olivetti port. — [MicroWeb src/DOS/BIOSVid.cpp](https://github.com/jhhoward/MicroWeb/blob/master/src/DOS/BIOSVid.cpp)
- MicroWeb has no separate Compaq or Olivetti driver file in the current tree. The whole of `src/DOS` is BIOSVid, Hercules, Surf1512, Surf4bpp, SurfVESA plus input/network/memory files; the 640x400 support is the table row above. — [MicroWeb repository](https://github.com/jhhoward/MicroWeb)
- The MicroWeb 640x400 support came from pull request 22 by mlaux. Its description says the mode is "available on the Olivetti M24, AT&T PC 6300, Compaq Portable II/III, and Toshiba T3100", "a mash up between ordinary CGA and Hercules, with the four-page interlacing behavior of Hercules but pretty much everything else from CGA", and that most machines "use BIOS mode `0x40`" while the Toshiba "uses BIOS mode `0x74`". The only real-hardware photo in the PR is "a real Toshiba T3100". — [MicroWeb PR 22](https://github.com/jhhoward/MicroWeb/pull/22)
- MAME's Portable III video card is a subclass of its Olivetti M24 card and wires 23C6h bit 0 to the same "400-line" flag: `m_mode2 = data & 1;` in `isa8_cga_cportiii_device::port_23c6_w`. The shared row renderer computes `uint16_t const offset = (((ma + i) << 1 ) & 0x1fff) | ((ra & 3) << 13);`, which is again bank = line mod 4, 8 KB per bank. — [MAME src/devices/bus/isa/cga.cpp](https://github.com/mamedev/mame/blob/master/src/devices/bus/isa/cga.cpp)

**The AT&T 6300 / Olivetti M24 for comparison**

- On the M24 the 400-line switch is port 3DEh bit 0. 86Box: `case 0x3de: ... ogc->ctrl_3de = val; /* select 1st or 2nd 16k vram block to be used */ ogc->base = (val & 0x08) ? 0x4000 : 0;` and, in the renderer, `/* 640x400 mode */ if (ogc->ctrl_3de & 1) { dat2 = ((ogc->cga.scanline & 1) * 0x4000) | (ogc->lineff * 0x2000);`. Bit 6 of 3DEh enables MDA-style underline in text (`underline = ((ogc->ctrl_3de & 0x40) && (attr & 0x1) && !(attr & 0x6));`). — [86Box src/video/vid_cga_olivetti.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_olivetti.c)
- MAME's M24 card agrees: `case 0x0e: m_mode2 = data; if((data & 8) && !(data & 1)) m_start_offset = 0x4000;` (offset 0Eh from 3D0h is 3DEh), with the comment "mode2 bit 0 only enables the 400 line mode; whether the display is text or graphics is still selected by bit 1 of the mode control register." — [MAME cga.cpp](https://github.com/mamedev/mame/blob/master/src/devices/bus/isa/cga.cpp)
- 86Box's Compaq plasma device registers I/O for 3D0h-3DFh but its write handler only acts on 3D0h-3D9h, 13C6h, 23C6h and 27C6h. A write to 3DEh falls to `default: break;` and does nothing. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- 86Box notes the M24's optional colour board is not emulated: "Optional EGC expansion board (which handles 640x400x16) not implemented". RBIL lists the matching AT&T-only modes (42h 640x400 16 colours, 41h 640x200 16 colours). The Compaq has no equivalent. — [86Box vid_cga_olivetti.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_olivetti.c); [RBIL](https://github.com/cirosantilli/ralf-brown-interrupt-list/blob/master/inter61a/INTERRUP.A)
- MAME's own header note for the Portable III describes the video as `AT&T 6300/Olivetti M24 driver compatible "Super CGA" with a 640x400 red/amber Plasma screen`. — [MAME src/mame/pc/at.cpp](https://github.com/mamedev/mame/blob/master/src/mame/pc/at.cpp)

**Other details that matter when writing straight to video memory (emulator model)**

- In mode 6 and in 640x400, the lit colour is `fg = (self->cga.cgacol & 0x0f) ? amber : black`. If the low nibble of the colour-select register (3D9h) is 0, the whole picture is black. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- Bit 3 of the mode-control register (3D8h) is the video enable: `if (!(self->cga.cgamode & 0x08)) ink = black;`. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- Bit 7 of each byte is the leftmost pixel (`ink = (dat & 0x80) ? fg : bg; ... dat <<= 1;`), and a 1 bit is a lit (amber) dot. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- The CRTC start address is added to every line address (`+ ((memaddr & ~1) << 1)`), so it must stay 0. All 32 KB is one page; there is no second page to flip to. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- The BIOS keeps its video parameter table short: "The video registers table (pointed to by INT 1Dh) is still only 64 bytes long, and therefore contains only the 6845 registers." Mode 40h's parameters are elsewhere in the ROM. — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)

**Detecting the plasma from a program**

- INT 10h AX=BF03h, BX=0000h ("Compaq Extensions - Get Environment") returns BH = active monitor (00h external, 01h internal), BL = master mode (04h CGA, 07h MDA), DH = internal monitor type, where `04h = 640x400 flat panel (Plasma CGA)`. — [VGADOC COMPAQ.TXT](https://pdos.csail.mit.edu/6.828/2018/readings/hardware/vgadoc/COMPAQ.TXT)
- John Elliott confirms the Portable III BIOS supports BF00h/BF01h (select external/internal monitor), BF02h (set master mode), BF03h (get environment), BF04h and BF05h (the last two "uses BL not BH"). — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)
- 86Box returns 40h from port 1BC6h and E6h from 17C6h, matching Elliott's readings. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)

### Inferences
- **Recipe to enter (inference from the sources above, not run on real hardware here):** `mov ax,0040h` / `int 10h`. RBIL, VGADOC and MicroWeb all point at BIOS mode 40h, and Elliott's port note explains what the BIOS must do underneath (set 23C6h bit 0).
- **Fallback if the BIOS call does not take (inference from the 86Box model):** set mode 6 with `mov ax,0006h` / `int 10h`, then `mov dx,23C6h` / `in al,dx` / `or al,01h` / `out dx,al`. Read-modify-write is required so bits 3-7 are kept. In 86Box this combination (hi-res graphics in 3D8h plus 23C6h bit 0) is exactly what selects the 640x400 renderer.
- **Recipe to leave (inference):** `mov ax,0003h` / `int 10h`. If bit 0 of 23C6h was set by hand, clear it first (`in al,dx` / `and al,0FEh` / `out dx,al`), because nothing found says the BIOS clears it on a normal mode set.
- **Address formula for the DOS program:** segment B800h. For 640x400, `offset = (y AND 3) * 2000h + (y SHR 2) * 80 + (x SHR 3)`. For mode 6, `offset = (y AND 1) * 2000h + (y SHR 1) * 80 + (x SHR 3)`. In both, bit 7 is the left pixel and 1 = lit.
- **Sizes:** 640x400 uses 4 x 8,000 = 32,000 bytes of the 32,768; mode 6 uses 2 x 8,000 = 16,000. At 115200 baud (11,520 bytes a second) a raw full screen takes about 2.8 s in 640x400 and 1.4 s in 640x200 (my arithmetic).
- **A delta format in "video memory order" should think in banks.** In 640x400 a vertical run of four screen lines touches four different 8 KB banks, so sorting changes by memory address scatters them down the screen in four passes. Trixter met the same thing on CGA's two banks and sorted deltas by "start offset compensated for CGA interlaced memory layout" (section 5).
- **Programs that enable the M24 mode by writing 3DEh directly are likely to fail on the Compaq.** 86Box ignores 3DEh on the plasma device, and Elliott's port list for the real machine has no 3DEh. Programs that call INT 10h mode 40h should work. MAME does accept 3DEh on its Portable III card, but only because that class inherits the M24 code, and MAME flags the machine as not working.
- The earlier notes' claim that the mode is "unique to Compaq's plasma machines" is wrong; RBIL lists the same mode 40h for the AT&T 6300 first. The earlier claims about mode 40h, port 23C6h bit 0, 32 KB at B800 and four interleaved 8 KB banks are confirmed.

### Gaps
- No source showed the Portable III ROM's mode 40h code, so it is not proven that INT 10h AX=0040h sets 23C6h bit 0, what it puts in 3D8h/3D9h, or whether INT 10h AH=0Fh then reports 40h (MicroWeb's check `GetScreenMode() == screenMode` depends on that). Test on the real machine or disassemble a ROM dump.
- Nobody was found reporting MicroWeb, or any other named program, running in 640x400 on a real Portable III. The MicroWeb PR shows a Toshiba T3100 only.
- Port 3DEh on the real Portable III is undocumented in every source read. "Ignored" is the 86Box model, not a measurement.
- The Compaq Portable III Technical Reference Guide was not found online in this session (bitsavers and archive.org were not searched exhaustively). It would settle all of the above.
- VGADOC adds nothing on 23C6h bit meanings; treat the earlier notes' "VGADOC (for mode 40h)" as covering the mode number only.

## 2. Text-mode attributes on the plasma, how the panel treats CGA 320x200 4-colour mode, and what else the BIOS exposes

### Takeaway
Text has three brightness states at most: off, full, and (by default) half intensity for "bright" text, which the plasma shows dimmer, not brighter. Graphics are strictly on or off; 86Box models 320x200 colours 0-3 as fixed 2x2 dot patterns at 0, 25, 50 and 100 percent. The BIOS also offers font loading, high-intensity mapping, monitor switching and a screen-save timer.

### Cited Findings

**What Compaq's own manual says**

- The Operations Guide lists the display's features: "High-resolution text (640 x 400, 80 characters x 25 lines)", "Graphics in three resolutions (640 x 400, 320 x 200, and 640 x 200)", "Built-in screen-save feature", "Support for an external color RGBI monitor", "User loadable character fonts (CHARSET)". — [Compaq Portable III Operations Guide, chapter 6 (archive.org OCR text)](https://archive.org/details/compaq-portable-3-operations-user-manual)
- Highlighted text is dimmer by default: "Many application programs provide highlighted text which appears brighter than surrounding text. On the plasma display, these characters are shown at a lower intensity than surrounding text. This is the default mode of the plasma display." — [Operations Guide, section 6.3](https://archive.org/details/compaq-portable-3-operations-user-manual)
- The selectable treatments of highlighted text are Half-Intensity (default), Reverse Video, Underline, Alternate Character Set, None, plus a Toggle that swaps which text gets the treatment. They are set with the ADAPT utility or the MODE command. — [Operations Guide, section 6.3](https://archive.org/details/compaq-portable-3-operations-user-manual)
- The display "supports both color (CGA) and monochrome (MDA) modes", chosen with `MODE SELECT=CGA` or `MODE SELECT=MDA`; "The CGA mode is the default when the system is turned on." There is also `MODE UNDERLINE ON|OFF`. — [Operations Guide, section 6.7](https://archive.org/details/compaq-portable-3-operations-user-manual)
- Table A-3 gives: graphic resolution 640 x 400, 320 x 200, 640 x 200; text resolution 640 x 400; type "DC Plasma"; character display 80/40 x 25; brightness adjustable. — [Operations Guide, appendix A](https://archive.org/details/compaq-portable-3-operations-user-manual)

**The registers and BIOS calls behind those options**

- Port 23C6h bits 5-7, "plasma high intensity attribute is treated as: 0 => Ignore, 1 => Reverse video, 2 => Underscore, 3 => Alternate font, 4 => Half intensity". Bit 4 is "Active intensity bit interpretation (toggled by INT 10h with AX=1402h and BL=0B1h)". — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)
- RBIL, INT 10h AX=1402h "SET MAPPING OF LCD HIGH INTENSITY ATTRIBUTES (CONV,CP386)": BL = `00h ignore high intensity attribute`, `01h map high intensity to reverse video`, `02h map high intensity to underscore`, `03h map high intensity to selected alternate font`, `B0h half intensity (Compaq)`, `B1h toggle active intensity bit interpretation (CP386)`. RBIL tags these for the IBM Convertible and the Compaq Portable 386. — [RBIL INTERRUP.A](https://github.com/cirosantilli/ralf-brown-interrupt-list/blob/master/inter61a/INTERRUP.A)
- RBIL, INT 10h AX=1400h loads a user font (ES:DI -> font, BH = bytes per character "08h or 10h (Compaq)", BL = 00h main / 01h alternate block, CX = count, DX = character offset); AX=1401h reloads the ROM default font. — [RBIL INTERRUP.A](https://github.com/cirosantilli/ralf-brown-interrupt-list/blob/master/inter61a/INTERRUP.A)
- John Elliott confirms the Portable III (286) BIOS supports these: "INT 10h / AH=14h (LCD functions) are supported, allowing the screen font to be loaded and the behaviour of high intensity attributes to be set." — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)
- There is no font ROM: "The font (8x8 or 8x16) is held in another bank of video RAM, and loaded by the BIOS at boot time." Character cells are always 16 rows high on the plasma. — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)
- Keyboard shortcuts in the BIOS: CTRL+ALT+< and CTRL+ALT+> switch between internal and external monitors; CTRL+ALT+minus "switches between MDA-compatible and CGA-compatible attributes in the 24x80 text modes". — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)

**How 86Box draws text attributes (emulator model)**

- Only two colours exist: `amber = makecol(0xff, 0x7d, 0x00); black = makecol(0x64, 0x19, 0x00);`. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- Its attribute table makes any foreground colour 1-7 show as amber on black whatever the background colour is; a foreground of 0 on a non-zero background shows as black on amber (reverse); equal foreground and background shows blank. The code comments read "Colours 07 and 0F are always amber on black" and "Exclude x0 and x8, which are always black on amber". — [86Box vid_cga_compaq_plasma.c, compaq_plasma_recalcattrs](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- Half intensity halves the brightness of cells with attribute bit 3 set when `(self->port_23c6 >> 5) == 4`. The alternate font is selected with `if (((self->port_23c6 >> 5) == 3) && hi_bit) chr_addr |= 0x1000;`. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- 86Box underlines any cell whose foreground is colour 1 (`underline = ((attr & 0x07) == 0x01);`), MDA style, on character row 7. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- **Conflict:** 86Box treats value 1 in 23C6h bits 5-7 as underline (`underline = underline || (((self->port_23c6 >> 5) == 1) && hi_bit);`) and value 2 as reverse video (`else if ((self->port_23c6 >> 5) == 2)` draws with the glyph inverted). — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c); contradicted by [John Elliott](https://www.seasip.info/VintagePC/compaq3.html) and [RBIL AX=1402h](https://github.com/cirosantilli/ralf-brown-interrupt-list/blob/master/inter61a/INTERRUP.A), which both give 1 = reverse video, 2 = underscore.

**CGA 320x200 4-colour mode (emulator model)**

- 86Box turns each 2-bit CGA pixel into a fixed 2x2 block of plasma dots, ignoring the palette. Pattern 0 is all black; pattern 1 lights one dot of four (`ink0 = amber; ink1 = black;` on even panel lines, both black on odd lines); pattern 2 lights two on a diagonal (even lines amber/black, odd lines black/amber); pattern 3 lights all four. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- 86Box's graphics paths write only `amber` or `black`; the half-intensity level is applied in the text paths only. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- The plasma code's history: reorganised into its own file on 2025-06-09, "Some small fixes to the Plasma (June 10th, 2025)" by TC1995, and "Complaq Plasma: Fix underline." by OBattler on 2026-08-09. It is still being corrected. — [86Box commit history for the file](https://github.com/86Box/86Box/commits/master/src/video/vid_cga_compaq_plasma.c)

### Inferences
- For the engineer's program, text mode gives a cheap third level: attribute 07h is full brightness and 0Fh is half brightness in the default setting. Graphics modes have no grey level, so all shading must be dithered.
- A 320x200 4-colour game should look like a 4-level picture (0/25/50/100 percent) on the plasma if 86Box's pattern table is right. The earlier notes' line "CGA's four colours show as dither patterns on the plasma, not shades" matches the emulator and nothing contradicts it, but no first-hand description of a real panel was found.
- Elliott's and RBIL's numbering (1 = reverse, 2 = underscore) is more likely correct than 86Box's, because Elliott read his own machine and RBIL documents the BIOS call that writes those bits. Do not rely on 86Box to preview reverse/underline mapping.
- A Wikipedia line found by search says the internal plasma shows "up to 16 shades of gray". That fits VGADOC's separate monitor type `08h = 16-level mono plasma VGA (internal)`, a later VGA plasma, and not the Portable III's type `04h = 640x400 flat panel (Plasma CGA)`. Treat the Portable III as two-level in graphics.

### Gaps
- No source describes how a real Portable III panel renders the four CGA colours. The pattern table is 86Box's.
- How `MODE UNDERLINE ON|OFF` and the "Toggle" option map to register bits was not found (bit 4 of 23C6h is the likely toggle, per Elliott's wording, but that is not stated outright).
- RBIL attributes INT 10h AH=14h to the Portable 386 and the IBM Convertible. That it also works on the Portable III rests on John Elliott's sentence alone.
- The Operations Guide's Appendix B, "COMPAQ DUAL-MODE PLASMA DISPLAY APPLICATION ..." (title cut off in the OCR), was not read. It may list tested applications and settings.

## 3. Emulators that cover the Portable III with its plasma display and the 640x400 mode: ROMs, host platforms, and connecting COM1 to a pty or socket

### Takeaway
86Box is the only emulator found with a working Portable III and a dedicated plasma device that implements 640x400. It ships a universal macOS build (Apple Silicon included) and, since v6.0, can expose COM1 as a host pseudoterminal. Its 32-bit ARM Linux builds stopped at v4.2.1, and the Compaq ROMs it needs are Compaq's copyrighted firmware.

### Cited Findings

**86Box**

- Machine table entry: `.name = "[ISA] Compaq Portable III"`, `.internal_name = "portableiii"`, CPU package 286 with bus 8-12.5 MHz, RAM 256-6784 KB, `.vid_device = &compaq_plasma_device`. There is also `"[ISA] Compaq Portable III (386)"` using the same plasma device. — [86Box src/machine/machine_table.c](https://github.com/86Box/86Box/blob/master/src/machine/machine_table.c)
- ROM it loads: `ret = bios_load_linearr("roms/machines/portableiii/K Combined.bin", 0x000f8000, 65536, 0);` and, when internal video is selected, `device_add(&compaq_plasma_device);`. — [86Box src/machine/m_at_286.c](https://github.com/86Box/86Box/blob/master/src/machine/m_at_286.c)
- The 86Box ROM repository holds `machines/portableiii/K Combined.bin` (32,768 bytes), `P.2 Combined.bin` (65,536), `109737-002.bin` and `109738-002.bin` (32,768 each), and `Compaq Portable III - BIOS - 106778-002 - Odd.bin` / `106779-002 - Even.bin` (16,384 each). Its README says only that it "contains all ROMs needed by the 86Box emulator"; it states no licence for them. — [86Box/roms repository](https://github.com/86Box/roms/tree/master/machines/portableiii)
- "K Combined.bin" matches a real machine: Elliott's Portable III has "32k of BIOS in two 16k chips", "revision K", dated 29 January 1987. — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)
- The plasma device is a fixed 640x400 panel at an assumed 60 Hz: `#define VID_CLOCK (double) (651 * 416 * 60)` under the comment `/*Very rough estimate*/`, and "Hardcode a fixed refresh rate and VSYNC timing" with vertical sync from line 400 to 416. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)
- Latest release: v6.0, published 2026-05-31, with assets `86Box-macOS-x86_64+arm64-b9001.zip`, `86Box-Linux-x86_64-b9001.AppImage`, `86Box-NDR-Linux-arm64-b9001.AppImage`, `86Box-NDR-Windows-ARM64-b9001.zip`, `86Box-Windows-64-b9001.zip`. No 32-bit ARM build. — [86Box releases](https://github.com/86Box/86Box/releases)
- The last release with a 32-bit ARM Linux build is v4.2.1 (2024-09-01): `86Box-NDR-Linux-arm32-b6130.AppImage`. Every release from v5.0 (2025-08-24) on lists only x86_64 and arm64 for Linux. — [86Box releases](https://github.com/86Box/86Box/releases)
- v4.2.1 already contains the Compaq plasma device with 23C6h handling (for example `if (!self->internal_monitor && !(self->port_23c6 & 1)) {` in `src/machine/m_at_compaq.c`). — [86Box v4.2.1 src/machine/m_at_compaq.c](https://github.com/86Box/86Box/blob/v4.2.1/src/machine/m_at_compaq.c)
- Serial in v6.0: each COM port can be attached to "Serial Passthrough" (a host serial port; "The host port's parameters (baud rate, parity, data bits and stop bits) are automatically configured to match the emulated port's parameters"), "Named Pipe", "File", or "Virtual Console". — [86Box v6.0 docs, Ports (COM & LPT)](https://86box.readthedocs.io/en/v6.0/settings/ports.html)
- Pseudoterminal: Virtual Console mode "*Create pseudoterminal* creates a PTY device, connects to it and displays its path when the machine is started." These modes are "only available on Linux and macOS hosts". The source confirms it: `dev->fd_in = dev->fd_out = posix_openpt(O_RDWR | O_NOCTTY | O_NONBLOCK);` followed by `char *pty = ptsname(dev->fd_out);` and a log line `"Bound to %s\n"`. — [86Box v6.0 docs](https://86box.readthedocs.io/en/v6.0/settings/ports.html); [86Box src/char/char_stdio.c](https://github.com/86Box/86Box/blob/master/src/char/char_stdio.c)
- Named pipes on Linux and macOS: "two pipes are created (adding `.in` and `.out` suffixes to the *Pipe path*) for bidirectional communication", and "the *Pipe path* can also point to a character device (such as a pseudoterminal ...)". — [86Box v6.0 docs](https://86box.readthedocs.io/en/v6.0/settings/ports.html)
- No TCP option appears in the v6.0 list of serial devices (None, Serial Passthrough, Named Pipe, File, Virtual Console), and the `src/char` directory holds only `char_file.c`, `char_fujinet.c`, `char_loopback.c`, `char_pipe.c`, `char_serial.c`, `char_stdio.c`. — [86Box v6.0 docs](https://86box.readthedocs.io/en/v6.0/settings/ports.html); [86Box src/char](https://github.com/86Box/86Box/tree/master/src/char)
- In v4.x the equivalent feature was "Serial port passthrough 1-4: Connect emulated serial ports to named pipes or serial ports on the host." — [86Box v4.0 docs](https://86box.readthedocs.io/en/v4.0/settings/ports.html)

**MAME**

- MAME has the machine but marks it broken: `COMP( 1987, comportiii,ibm5170, 0, comportiii,0, at_state, init_at, "Compaq", "Portable III", MACHINE_NOT_WORKING )`, with the note "To-Do: Emulate Graphics card fully". — [MAME src/mame/pc/at.cpp](https://github.com/mamedev/mame/blob/master/src/mame/pc/at.cpp)
- Its ROM set: `cpiii_87c128_106779-002.bin` and `cpiii_87c128_106778-002.bin` (0x4000 each), or `109738-002.bin` and `109737-002.bin` (0x8000 each). The video card "cga_cportiii" has no ROM of its own (`ROM_FILL(0, 0x2000, 0)`), because the font lives in RAM. — [MAME at.cpp](https://github.com/mamedev/mame/blob/master/src/mame/pc/at.cpp); [MAME cga.cpp](https://github.com/mamedev/mame/blob/master/src/devices/bus/isa/cga.cpp)
- MAME's card implements only part of the hardware: 23C6h bit 0 (400-line) and bit 3 (font RAM mapping); reads of 23C6h always return 0 (`return 0;`), 13C6h always returns 04h, and writes to 13C6h do nothing. — [MAME cga.cpp](https://github.com/mamedev/mame/blob/master/src/devices/bus/isa/cga.cpp)

**PCem**

- PCem's model list has "[8088] Compaq Portable Plus", "[8086] Compaq Deskpro", "[286] Compaq Portable II", "[386DX] Compaq Deskpro 386" and "[286] Toshiba T3100e". There is no Portable III. Its only plasma code is for Toshiba machines (`src/video/vid_t3100e.c`, `vid_t1000.c`). — [PCem src/models/model.c](https://github.com/sarah-walker-pcem/pcem/blob/dev/src/models/model.c)
- 86Box's Compaq plasma file credits "Sarah Walker" (PCem's author) alongside Miran Grca in its header, with copyright years 2008-2020. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c)

**DOSBox family**

- DOSBox Staging describes its graphics emulation as "text mode, Hercules, CGA, EGA, VGA, VESA, S3 Trio 64, and Tandy hardware"; the AT&T/Olivetti mode is not in that list (search snippet). — [DOSBox Staging](https://dosbox-staging.org)
- An older Vogons post says of the AT&T 640x400x2 mode that "apparently no emulators can use this mode" (search snippet; the thread predates 86Box's plasma and M24 work). — [Vogons post 283310](https://www.vogons.org/viewtopic.php?p=283310)

### Inferences
- For building and testing the DOS receiver before the real machine is ready, 86Box v6.0 on the Apple Silicon Mac is the right rig: Portable III machine, plasma device, mode selected by 23C6h bit 0, and COM1 on a pty that the Pi-side sender script can open like a serial port. A TCP link needs a bridge such as `socat` between the pty and a socket; 86Box has no TCP serial device.
- The current test rig (DOSBox at 286 speed) cannot show mode 40h, so 640x400 code cannot be tested there. Mode 6 code can.
- On the Raspberry Pi 3 B+: with a 64-bit OS the arm64 AppImage should start; with a 32-bit OS the newest usable build is v4.2.1. Either way a Pi 3 is a weak host for 86Box. This is an estimate; no benchmark of 86Box on a Pi 3 was found.
- The only clearly legitimate ROM source is a dump of the engineer's own machine's two BIOS chips. The 86Box and MAME sets are the same Compaq firmware passed around by the emulation community with no licence shown. Check the BIOS revision of the real machine against "K" before trusting emulator behaviour.
- Emulator timing is not hardware timing. 86Box's refresh rate, video-memory wait states (`int ws_array[16] = { 3, 4, 5, 6, 7, 8, ...}`) and serial behaviour are approximations, so frame rates and maximum baud rates measured in 86Box are indications only.

### Gaps
- Whether 86Box's BIOS mode 40h actually works end to end with the K ROM was not run in this session; only the source was read.
- Whether v4.2.1's passthrough can create a pty (as opposed to named pipes and host serial ports) was not checked in its source.
- How accurately 86Box emulates the UART on this machine (8250/16450, no FIFO) and receive overruns at 115200 was not examined.
- MAME's general ability to route a serial port to a socket, and its Apple Silicon and ARM Linux support, were not looked up, because the machine is flagged not working.
- MartyPC, PCjs, DOSBox-X and VARCem were not checked in source for a Compaq plasma or mode 40h; the search found no claim that any of them has it.

## 4. The plasma panel: model, refresh behaviour, persistence, burn-in guidance, and what matters for moving pictures

### Takeaway
Compaq documents the panel only as a 10-inch "DC Plasma" display, 640x400, with a brightness knob and a screen-save timer that blanks it after 15 minutes without activity by default. The panel's part number, true refresh rate and persistence could not be confirmed; the "MD400F640PD5" in the earlier notes is unverified.

### Cited Findings
- Compaq's specification table: viewing area diagonal 10.0 in (25.4 cm), height 5.2 in (13.2 cm), width 8.3 in (21.1 cm); "Type: DC Plasma"; "Mounting: Internal"; "Brightness: Adjustable". — [Operations Guide, Table A-3](https://archive.org/details/compaq-portable-3-operations-user-manual)
- Screen-save: "The screen-save feature automatically blanks the plasma display after a specified time interval without activity. This prevents private information from being readily viewed while unattended." Compaq presents it as privacy, not as panel protection. — [Operations Guide, section 6.2](https://archive.org/details/compaq-portable-3-operations-user-manual)
- `MODE SCREEN-SAVE` sets the interval "anywhere from 0 to 63 minutes. The default is 15 minutes. This means that if 15 minutes elapse without an entry from the keyboard or other computer activity, the screen goes blank. Pressing any key reactivates the screen. Pressing the SHIFT key reactivates it without any action being taken on the computer". — [Operations Guide, section 6.7](https://archive.org/details/compaq-portable-3-operations-user-manual)
- The hardware register behind it: `27C6h [r/w] Bits 0-5: Plasma timeout in minutes, 0-3Fh. Bits 6-7: Unknown. Always 0 when written; masked off when read.` — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html)
- The BIOS can blank or unblank the display: INT 10h AX=BF05h, "Enable/Disable Display", with the Portable III taking the value in BL (Elliott: "uses BL not BH"); VGADOC lists the values as 00h off, 01h on. — [John Elliott](https://www.seasip.info/VintagePC/compaq3.html); [VGADOC COMPAQ.TXT](https://pdos.csail.mit.edu/6.828/2018/readings/hardware/vgadoc/COMPAQ.TXT)
- Brightness is a physical knob at the lower-right corner of the display. — [Operations Guide, section 2.12](https://archive.org/details/compaq-portable-3-operations-user-manual)
- Emulators draw the panel as orange on a dark red-brown that is never fully black: 86Box `amber = makecol(0xff, 0x7d, 0x00); black = makecol(0x64, 0x19, 0x00);`, MAME `set_color(rgb_t(255, 125, 0))` and `set_pen_color(0, 100, 25, 0)`. — [86Box vid_cga_compaq_plasma.c](https://github.com/86Box/86Box/blob/master/src/video/vid_cga_compaq_plasma.c); [MAME cga.cpp](https://github.com/mamedev/mame/blob/master/src/devices/bus/isa/cga.cpp)
- MAME's hardware note lists the Portable III graphics chip as "Graphics: M77H010". — [MAME at.cpp](https://github.com/mamedev/mame/blob/master/src/mame/pc/at.cpp)
- A general repair guide for these gas-plasma panels says they "operate at voltages around 100 - 300 volts or more", that burn-in is "typically caused by wear and tear" and shows as ghosting or darkened patches that "cannot be repaired", and that dead or bright lines usually come from the driver ICs. The page names no panel part numbers and is not specific to the Portable III. — [Retropaq, Repairing gas plasma displays](https://retropaq.com/repairing-gas-plasma-displays/)
- A restoration write-up says the Portable III power supply has a connector with "2 x 200v rails for the Gas Plasma screen" (search snippet). — [ret.rocks, Compaq Portable III](https://ret.rocks/index.php/one-off-works/compaq-portable-iii)
- A parts supplier lists the Panasonic MD400F640PD1A as a 9.4-inch 640x400 plasma panel; the listing does not mention Compaq (search snippet). A 1997 mailing-list post describes an MD400F640PD2A as a DC-type graphic plasma display believed to be made by Matsushita (search snippet). — [slw-ele listing](https://www.slw-ele.com/md400f640pd1a.html); [piclist post, 1997](https://pic.hallikainen.org/piclist/1997/06/11/043420a.txt)
- A Vogons owner reports that turning on an external CGA monitor turns the plasma off; the machine has no dual-display mode (search snippet). — [Vogons post 1140728](https://www.vogons.org/viewtopic.php?p=1140728)

### Inferences
- **The screen-save timer will blank a video.** A player that reads the serial port and never touches the keyboard may count as "no activity", so the panel could go dark 15 minutes into a clip. The receiver should either raise the timeout at start (`MODE SCREEN-SAVE`, ADAPT, or port 27C6h) and restore it on exit, or the Pi should pause for a key. Whether serial interrupts or video writes count as "other computer activity" is not documented.
- The Matsushita/Panasonic MD400F640 family is the right kind of part (DC plasma, 640x400), but Compaq's own 5.2 x 8.3 in viewing area works out to a 9.8 in diagonal, against the supplier's 9.4 in for the PD1A, and no source ties any suffix (PD1A, PD2A, PD5) to the Portable III. The exact model is unconfirmed.
- Burn-in advice for moving pictures has to be common sense, not sourced guidance: avoid a fixed bright frame or status bar left on for hours, keep the knob below maximum, and keep the timer on when idle.
- Because 640x200 content is shown line-doubled, a mode 6 picture lights two panel rows per data row, while 640x400 lights exactly the dots you send. That halves the data needed for the same lit area but not the wear.

### Gaps
- Panel manufacturer and model for the Portable III: not found in Compaq's guide, John Elliott's page, or the emulator sources. Reading the label on the real panel is the way to settle it.
- Real refresh rate and scan method: not found. 86Box's 60 Hz is flagged in its own source as a "Very rough estimate".
- Persistence, response time and any motion smear: nothing found, sourced or anecdotal.
- Whether a timeout value of 0 disables the screen-save: the manual gives the range 0-63 and does not say what 0 does.
- Manufacturer burn-in or lifetime figures: none found.
- Whether the CGA status port (3DAh) gives a usable vertical-sync signal on the real machine for tear-free updates: only 86Box's emulated behaviour is known.

## 5. Proven 1-bit video techniques and their numbers; which dithering stays stable between frames and compresses best with delta plus run-length coding

### Takeaway
Every working project found sends only the bytes that changed and uses a dither whose output for one pixel does not depend on its neighbours (ordered/Bayer, or a blue-noise mask), because error diffusion changes most of the screen every frame. The closest proven case to this link is the Apple II over 115200 baud: 7-8 fps full screen at 280x192, more at smaller sizes.

### Cited Findings

**8088 Domination and XDC (IBM PC 5150, 4.77 MHz 8088, CGA, played from hard disk)**

- The bandwidth problem in the author's words: "Even a simple calculation assuming 24fps video reveals that the amount of data needing to be updated per second (24fps * 16KB = 384KB/s) is outside of the IBM PC's capability: CGA RAM can only be changed at a rate of 240KB/s, and most hard drives of the era operate at roughly 90KB/s." — [Trixter, 8088 Domination Post-Mortem, Part 1](https://trixter.oldskool.org/2014/06/19/8088-domination-post-mortem-part-1/)
- Why ordered dither: "What we need is a so-called stable or localized dither, where the value of each output pixel does not depend on its neighbors." and "the only truly localized dithering algorithm I know of is ordered dithering, sometimes called Bayer dithering." Error-diffusion dithers were rejected because the error spreads across the whole picture. — [Trixter, Part 1](https://trixter.oldskool.org/2014/06/19/8088-domination-post-mortem-part-1/)
- Encoding: each change is a "delta" with a start and end offset in screen memory. A "run" is a delta whose bytes are all the same (replayed with REP STOSB); a "slice" is one whose bytes differ (replayed with REP MOVSB). Deltas are sorted longest first, runs before slices at equal length, and optionally by "start offset compensated for CGA interlaced memory layout" so changes paint top to bottom. The encoder fills a per-frame byte budget and a CPU-cycle budget, and leftover changes carry into the next frame or are dropped. — [Trixter, Part 1](https://trixter.oldskool.org/2014/06/19/8088-domination-post-mortem-part-1/)
- CPU budget: "# of cycles available to us to paint a frame: About 40,000 ... # of cycles used by branches to replay 600 deltas: 14,400 (36% of our total)". That overhead is why each frame is stored as x86 code instead of data. — [Trixter, 8088 Domination Post-Mortem, Conclusion](https://trixter.oldskool.org/2014/06/20/8088-domination-post-mortem-conclusion/)
- The earlier data-driven delta record was: bytes 0-1 start offset; byte 2 length in the upper 7 bits with a run flag in bit 0; byte 3 fill value; then the data bytes (as summarised from the article by an automated reader). — [Trixter, Conclusion](https://trixter.oldskool.org/2014/06/20/8088-domination-post-mortem-conclusion/)
- Result: the Bad Apple section runs "at 640x200 resolution at 30 frames per second" on the 5150 (quoted from a pingback on the article; Wikipedia states the same), from "an extremely clean 30fps source". — [Trixter, Part 1 (pingbacks)](https://trixter.oldskool.org/2014/06/19/8088-domination-post-mortem-part-1/); [Trixter, Conclusion](https://trixter.oldskool.org/2014/06/20/8088-domination-post-mortem-conclusion/)
- XDC ("X86 Delta Compiler") is the released tool: "Up to 60 FPS playback, depending on the material and host system", variable bitrate with a settable maximum, a Sound Blaster for audio, a hard disk for larger files. — [x86dc.wordpress.com](https://x86dc.wordpress.com/)
- Source and binaries: the repository has `XDC_COMP.EXE` and `XDC_PLAY.EXE` under `compiled/`, plus an example `palette/example_640x200.bmp`. It is "written entirely in 16-bit real-mode pascal with some inline assembler" and needs Turbo Pascal 7.0 to build. — [MobyGamer/XDC](https://github.com/MobyGamer/XDC)

**Apple II over a serial cable (the nearest match to this project)**

- Link: "a good, stable 115200bps on the serial link", about 11.52 kB/s, to a 1 MHz 6502. The hi-res page is 8 KB (280x192, 7 pixels per byte). — [Colin Leroy-Mira, How I stream video through an Apple II's serial port](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)
- Measured frame rates with Bad Apple: about 7-8 fps at full-screen 280x192, about 14-15 fps at 210x144, about 22 fps at 140x96. — [Colin Leroy-Mira](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)
- Protocol: the sender diffs each frame against the last and sends only changed bytes. Memory is split into 65 "bases" of 126 positions each (65 x 126 is about one 8 KB page); a control byte (high bit set) moves the write position, data bytes then write and auto-advance, so neighbouring changes cost no address bytes. A marker byte plus count plus value encodes repeats, used only for runs of 3 to 7. Each frame starts with an unconditional "base 0, offset 0" to resynchronise. — [Colin Leroy-Mira](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)
- Pacing: target 24 fps (41.6 ms per frame); if the client falls more than a frame behind, the server skips frames. The client sends one byte back per frame (space pauses, escape stops). — [Colin Leroy-Mira](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)
- Dither: ordered. The author prefers error diffusion to look at, but it makes nearly every frame differ from the previous one and defeats the delta coding. — [Colin Leroy-Mira](https://www.colino.net/wordpress/archives/2024/03/11/how-i-stream-video-through-an-apple-iis-serial-port/)
- Code: client `surl_stream.s` under `src/lib/surl/`, server `stream.c` under `src/surl-server/helpers/`. — [colinleroy/a2tools](https://github.com/colinleroy/a2tools)

**Compact Macintosh: MacFlim (512x342 1-bit, played from disk, not streamed)**

- Bandwidth is set as a "byterate", bytes per tick (1/60 s): "The Mac Plus is able to read and decode around 1500 bytes per tick, the Mac SE around 2500, and the Mac SE/30 6000." Sound adds about 370 bytes per tick. — [fstark/macflim README](https://github.com/fstark/macflim)
- Low-end profiles: 128K "byterate of 380 bytes", 512K "480 bytes per ticks", XL "580 bytes per ticks", each with the frame rate divided by 4 and no sound. — [macflim README](https://github.com/fstark/macflim)
- When the budget runs out, the encoder "will let part the previous frame leak into the next one". The Plus and SE profiles also skip half the frames (`--fps-ratio 2`). — [macflim README](https://github.com/fstark/macflim)
- Dither choice by machine: "The Mac Plus uses `ordered` encoding by default while the Mac SE and SE/30 use the `error` encoding (floyd algorithm)." With error diffusion "the number of pixels changing from one frame to another is higher, so it uses more bandwidth for encoding." — [macflim README](https://github.com/fstark/macflim)
- Blue noise: "A new 'blue' dithering that is as efficient to encode as the 'ordered' dithering, but looks much closer to the 'error' dithering", "using a 256x256 texture". — [macflim README](https://github.com/fstark/macflim)
- Temporal tricks for error diffusion: `--error-stability` ("makes the dithered pattern match the preceding frame more closely"; defaults 0.5 for Plus and SE, 0.3 for SE/30; "a high stability will cause artifacts"), `--error-bleed` (fraction of error passed on: 0.98 Plus, 0.99 SE and SE/30; "Lower values of bleed make changes more local"), and `--error-bidi` (alternate direction per line). — [macflim README](https://github.com/fstark/macflim)
- Pre-filters that cut bandwidth: blur ("generally enables a better encoding by smoothing out details"), quantise to 17 levels ("particularly useful when using ordered dithering, as there are only 17 different dithering patterns"), and a black-crush filter that removes the darkest 6.25% because stray white dots in dark areas are "visually distracting (and eats encoding bandwidth)". — [macflim README](https://github.com/fstark/macflim)

**Dithering stability in general**

- FFmpeg's "a_dither" and "x_dither" (position-only arithmetic dithers) were added with the claim that for GIF they are "often more than twice as good at compression" and show less flicker than error diffusion (author's claim, search snippet). — [FFmpeg commit log, March 2014](https://ffmpeg.org/pipermail/ffmpeg-cvslog/2014-March/075712.html)
- Pixman replaced plain Bayer with a 64x64 ordered matrix built from blue noise because Bayer's regular pattern caused visible artefacts when gradients moved (search snippet). — [pixman make-blue-noise.c](https://gitlab.freedesktop.org/pixman/pixman/-/blob/9b49f4e08751885289333fed652bf5e0f45976b4/pixman/dither/make-blue-noise.c)
- Lucas Pope's Return of the Obra Dinn work is the best-known write-up of 1-bit dither that does not "swim" in motion; it is about a moving 3D camera, where he pinned the pattern to a sphere around the viewer (secondhand summary, search snippet). — [Set Side B on the Obra Dinn dithering post](https://setsideb.com/?p=5672)

### Inferences
- **Ranking for delta plus run-length coding (inference from the projects above; no published head-to-head test was found):**
  1. Ordered (Bayer) dither: fully stable, fewest changed bytes, and still areas turn into repeating byte pairs that run-length coding eats. It shows a visible crosshatch.
  2. A fixed blue-noise mask (same mask every frame): equally stable, since each pixel is still compared with a fixed threshold, with a more natural look. MacFlim reports it is as cheap to encode as ordered. Runs are shorter than with Bayer, so plain RLE gains less; delta still works well.
  3. Error diffusion with temporal damping (MacFlim's stability, bleed and two-direction options): best stills, most changed bytes, only for a faster link.
  4. Plain Floyd-Steinberg per frame: avoid. Three independent projects dropped it for the same reason.
- **Do not change the mask from frame to frame.** Animated or per-frame blue noise helps on displays that average over time, but here it would change almost every byte every frame.
- **Pre-filters are cheap wins on the Pi:** a slight blur, quantising grey levels to the number of patterns the dither can show (17 for a 4x4 Bayer matrix), and crushing near-black to pure black.
- **Frame-rate expectation for this link (estimate).** The Apple II result implies about 11,520 / 7.5 = roughly 1,500 changed-data bytes per frame for Bad Apple at 8 KB per screen, which is about 19% of the frame. At the same ratio, 640x200 (16,000 bytes) would manage about 3.8 fps and 640x400 (32,000 bytes) about 1.9 fps, and a 320x200-pixel window on the mode 6 screen (8,000 bytes) about 7 fps. Bad Apple is unusually easy (flat black and white shapes); dithered live action will be worse, and a 286 can afford better compression than the Apple II's 3-to-7 run limit, which pulls the other way.
- **MacFlim's lowest profile is still about twice this link.** 380 bytes per tick is 22,800 bytes a second for 512x342 at a quarter frame rate, against 11,520 here. Its "let the old frame leak through when the budget runs out" rule is the right behaviour to copy: a fixed byte budget per frame, biggest changes first (Trixter's sort order), remainder carried over.
- **Trixter's compiled-code trick is not needed.** His limit was 40,000 CPU cycles per frame on a 4.77 MHz 8088 fed from a 90 KB/s disk. Here the cable is the limit by a wide margin, so a simple data-driven decoder (offset, length, run flag, bytes) is enough.
- **Borrow from the Apple II protocol:** an unconditional position reset at the start of each frame for resynchronisation after a lost byte, auto-advancing writes so neighbouring changes need no address, and a one-byte reply per frame for pause, stop and flow control.

### Gaps
- No measured comparison of Bayer, blue-noise and damped error diffusion under delta plus RLE was found. The ranking above is reasoned from what the three projects chose and say.
- XDC's actual data rates for 640x200 (bytes per frame, KB per second, file size per minute) were not found on the pages that could be read. An automated summary of Trixter's conclusion article reported "at least 120KB/s", which matches the earlier notes' "about 120 KB per second", but a text search of the article body did not find that figure, so treat it as unverified.
- No standalone "Bad Apple on CGA" or "Bad Apple on Hercules" player project with published numbers was found beyond 8088 Domination itself.
- No compact-Macintosh project that streams video over a serial link was found; MacFlim plays from disk.
- Trixter's Part 2 article (the one between Part 1 and the Conclusion, if distinct) was not read.
- Whether XDC's player runs correctly on a 286 with the Compaq's CGA-compatible hardware was not found; its FAQ says only that videos "will play properly on any x86 computer that can run DOS" (as summarised by an automated reader).

## 6. Native DOS graphics programs worth running on a 286 with mono CGA 640x200 or the 640x400 mode

### Takeaway
Doom8088 has a dedicated 286 build for CGA 640x200 two-colour (`D286CBW.EXE`), and Wolfenstein 3D CGA and MicroWeb both have modes that fit, but no measured frame rate on a 12 MHz 286 was found for either game. Wolfenstein's only 640x200 mode is an inverted one meant for LCDs.

### Cited Findings

**Doom8088 (FrenkelS)**

- Scope: "a port for PCs with a 16-bit processor like an 8088 or a 286, and with MDA, CGA, EGA, VGA or MCGA graphics." "It uses 64 kB of EMS memory, if available, as an upper memory block to store data. And 1507 kB of XMS memory, if available, as a RAM drive." Episode 1 only, PC speaker sound effects, no music, no saving, no mouse. — [FrenkelS/Doom8088 README](https://github.com/FrenkelS/Doom8088)
- The CGA two-colour build arrived in release v20250108: "CGA 640x200 2 color mode (D286CBW.EXE and D8088CBW.EXE)". This confirms the file name in the earlier notes. — [Doom8088 release v20250108](https://github.com/FrenkelS/Doom8088/releases/tag/v20250108)
- The CGA four-colour build arrived in v20241226: "This release brings the CGA 320x200 4 color mode version ... Press F5 to switch the palette." — [Doom8088 release v20241226](https://github.com/FrenkelS/Doom8088/releases/tag/v20241226)
- Other builds that suit this machine: MDA 80x25 text (`D286MDA.EXE`) and CGA-compatible text modes 80x25 and 40x25 (`D2T80X25.EXE`, `D2T40X25.EXE`). — [Doom8088 release v20241223](https://github.com/FrenkelS/Doom8088/releases/tag/v20241223)
- Latest release: v20260304 (2026-03-04), "Optimized BSP trees thanks to ZenNode" and "More math code in assembly", with a `DOOM8088-CGA-v20260304.zip`. — [Doom8088 releases](https://github.com/FrenkelS/Doom8088/releases)
- Benchmark and counter: `-timedemo demo3` runs the benchmark, and the IDRATE cheat toggles an FPS counter ("Divide by 10 to get the real FPS"). `-noems`, `-noxms`, `-nosfx` are available. — [Doom8088 README](https://github.com/FrenkelS/Doom8088)
- It needs a WAD preprocessed by jWadUtil. — [Doom8088 README](https://github.com/FrenkelS/Doom8088)
- The only frame-rate report found: a Vogons user said "in my 286 25mhz, the speed is great, a benchmark give me 15fps", build and video mode not stated (search snippet). — [Vogons post 1317557](https://www.vogons.org/viewtopic.php?p=1317557)

**Wolfenstein 3D CGA (jhhoward)**

- It is "a modification to the original Wolfenstein 3D source release which renders the game in CGA video modes", changed "so that it can be run on 8088 based CPUs". — [jhhoward/WolfensteinCGA README](https://github.com/jhhoward/WolfensteinCGA)
- Modes: default 4-colour "mode 5" red palette; `classic` (mode 4 magenta palette, "avoids directly manipulating CGA registers so may be preferable for clone cards"); `composite`; `tandy` (160x200, 16 colours); `lcd` ("run in 640x200 monochrome with the colours inverted. This mode is useful for laptops and palmtops which invert the screen colour"); `lcd wide`. — [WolfensteinCGA README](https://github.com/jhhoward/WolfensteinCGA)
- Benchmark: `WOLF3DC.EXE timedemo` plays a demo as fast as possible and reports average frames per second. — [WolfensteinCGA README](https://github.com/jhhoward/WolfensteinCGA)
- Releases: v1.0 (2023-01-19) with a shareware-based demo zip; the registered game needs version 1.4 data converted with `cgaify.exe` on a modern Windows machine. A separate experimental Tandy 320x200 build was posted 2026-04-14. — [WolfensteinCGA releases](https://github.com/jhhoward/WolfensteinCGA/releases)
- Measured speed, slower machine: on a Tandy 1000EX with a V20 CPU the benchmark "averaged 3.6 fps", rising to 5.8 fps with the view shrunk to about 60% (search snippet). — [Dave Farquhar, Wolfenstein 3D for CGA and Tandy](https://dfarq.homeip.net/wolfenstein-3d-for-cga-and-tandy)
- A Vogons user posted screenshots from "a Hercules-equipped small 286 12MHz computer with CGA emulation", with no frame rate (search snippet). — [Vogons post 1134804](https://vogons.org/viewtopic.php?p=1134804)

**Programs with AT&T / Olivetti 640x400 support**

- MicroWeb: v0.53 (2023-07-08) "Added support for 640x400 mode used by Olivetti M24, AT&T PC 6300, Compaq Portable II/III, and Toshiba T3100 (thanks to @mlaux)". v2.0 (2024-04-17) added GIF display, tables, forms and EMS use; v2.1 (2026-03-12) added XMS support and file download. The menu entry is "640x400 monochrome (Olivetti M24)", BIOS mode 40h. — [MicroWeb releases](https://github.com/jhhoward/MicroWeb/releases); [MicroWeb src/VidModes.cpp](https://github.com/jhhoward/MicroWeb/blob/master/src/VidModes.cpp)
- MicroWeb also offers "640x200 monochrome (CGA)" (mode 6), which needs no special hardware. — [MicroWeb src/VidModes.cpp](https://github.com/jhhoward/MicroWeb/blob/master/src/VidModes.cpp)
- A Vogons post lists Windows, GeoWorks, Fractint, Lotus 1-2-3, Microsoft Word, Turbo Pascal and PC Paintbrush as supporting the AT&T/Olivetti 640x400 mode, and says MobyGames lists two games for it, Colony (Mindscape) and Space Wars (Keypunch Software) (search snippets). — [Vogons post 713981](https://www.vogons.org/viewtopic.php?p=713981); [Vogons post 283310](https://www.vogons.org/viewtopic.php?p=283310)
- An unofficial Sierra SCI0 driver for the 640x400 monochrome mode exists, named ATT320.DRV in the source that mentions it (search snippet). — [roybaer/foss_sci_drivers](https://github.com/roybaer/foss_sci_drivers)
- For Windows on the plasma, Wikipedia's Portable 386 article says CGA mode is mandatory for "Microsoft Windows' Compaq Plasma Driver" (Portable 386, search snippet). — [Wikipedia, Compaq Portable 386](https://en.wikipedia.org/wiki/Compaq_Portable_386)
- The Operations Guide's OCR text contains no occurrence of "AT&T", "Olivetti", "GEM" or "Windows" in connection with display drivers (word search of the full text). — [Operations Guide (archive.org OCR text)](https://archive.org/details/compaq-portable-3-operations-user-manual)

**Demos**

- 8088 Domination's player and the XDC encoder are the notable 640x200 two-colour demo material; XDC's repository ships a 640x200 example bitmap and the DOS player. — [MobyGamer/XDC](https://github.com/MobyGamer/XDC)

### Inferences
- **Doom8088:** use `D286CBW.EXE` (640x200 two-colour, dithered) first. `D286C*.EXE` in 320x200 four-colour is the alternative; on the plasma it would show as four dot densities if the 86Box pattern table is right. The earlier notes' "3-5 fps" on this machine stays an estimate: the only report found is 15 fps on a 25 MHz 286 in an unstated mode. Scaling that by clock speed alone would suggest roughly 7 fps at 12 MHz, but the build is unknown, so run `-timedemo demo3` on the real machine.
- **Wolfenstein 3D CGA:** the earlier notes' "640x200 one-colour mode" is the `lcd` mode, which is inverted for LCDs. On the plasma, where a 1 bit is a lit dot, it will most likely look like a photographic negative. The default four-colour mode (or `classic`, which avoids direct register writes) is the safer first try. A 12 MHz 286 should be well above the V20's 3.6 fps, but no number was found.
- **640x400 software on the Compaq:** anything that asks the BIOS for mode 40h (MicroWeb does) has a good chance. Anything written for the M24 that writes port 3DEh itself, or that expects the M24's 16-colour board, probably will not work. None of the listed applications or games was found confirmed on a real Portable III.
- The earlier notes' statement that "Compaq's manual says to use the AT&T/Olivetti 640x400 drivers in Windows and GEM" is not supported by the Operations Guide. It may come from another Compaq document (the Supplemental Software Guide or a Windows readme), or from MAME's description of the video as "AT&T 6300/Olivetti M24 driver compatible". Treat it as unverified.
- All three (Doom8088, Wolfenstein, MicroWeb) need files larger than is comfortable to send over a 9600 baud Kermit session, so they depend on the hard disk or a floppy route more than on the graphics work.

### Gaps
- No measured Doom8088 or Wolfenstein 3D CGA frame rate on a 10-12 MHz 286 was found. Vogons threads that probably hold them could not be opened from this environment.
- The exact executable names inside the current Doom8088 CGA zip were not checked (the zip was not downloaded); `D286CBW.EXE` is confirmed by the v20250108 release note only.
- Whether Doom8088's and Wolfenstein's direct CGA register writes behave on the Compaq's CGA-compatible controller is untested.
- No list of games confirmed working in 640x400 on a Compaq plasma was found. Colony and Space Wars come from a secondhand mention of MobyGames, and which versions support the mode was not checked.
- Which Windows 1.x/2.x/3.x display driver is correct for the Portable III's plasma (a Compaq plasma driver, or the AT&T 6300 / Olivetti one) was not confirmed from a primary source.
- Demos that target the AT&T 640x400 mode: none found.
