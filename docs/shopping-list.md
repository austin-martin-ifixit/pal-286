# Shopping list for the Compaq

Prices were read from each seller's page on 13 October 2026. Amazon and eBay
prices move daily. "Not confirmed" means no source could be found for this
exact machine, so look before buying.

## Seen inside (2026-10-15, Austin's photos)

There is no floppy ribbon. The Epson 1.2 MB drive's card edge goes into a
small adapter that plugs straight onto a 34-pin male header on the board
behind the bay, and the GoTEK has male pins too: a 34-pin cable with
two-row plugs joins them. The drive's power plug is the large 4-pin one, so
the GoTEK (small plug) needs an adapter. The hard disk's 40-pin cable
carries only its signals (power is separate), and can't be joined to the
Pi's 40-pin header: the pins don't match (the Pi's 5 V would meet ground)
and the Pi's 3.3 V inputs can't take the Compaq's 5 V.

Still to look at:

| Look at | What you'll see | What it decides |
|---|---|---|
| The main chip on the GoTEK's board | AT32F415 or AT32F435 | Which FlashFloppy file to load (no purchase) |

## Ordered on 15 October, arriving 20 October

| Item | For | Price |
|---|---|---|
| CablesOnline FF-001 floppy cable | The board's floppy header to the GoTEK. A "universal" PC cable: two-row plugs for 3.5-inch drives as well as card-edge ones | $14.98 |
| ThtRht floppy power adapters, 4-pack | The Compaq's large plug to the GoTEK's small one, and the same for the CompactFlash adapter; two spare | $7.97 |
| Monoprice 105441 USB A-to-A cable | Flashing FlashFloppy onto the GoTEK, from the Pi | $5.10 |
| StarTech BRACKETFDBK bay bracket | Holds the 3.5-inch GoTEK in the 5.25-inch bay. Fit in this bay is not confirmed; one owner trimmed a mount | $6.37 |
| SinLoon CF-to-IDE adapter, 40-pin male | A CompactFlash card in place of the 37-year-old hard disk, on its 40-pin cable | $8.59 |
| 4 GB CompactFlash card, listed as SanDisk Ultra II (SDCFH-004G) | Sold by a third party, "HUADAWEI": SanDisk stopped making this card years ago, so it's likely a relabelled one. Test it with f3probe on the Pi first (README, "When the hardware arrives") | $16.98 |
| PC speaker bar | PAL's voice once the TV goes away | $12.31 |
| Clock battery (ordered by Austin on eBay) | Without it the Compaq forgets its settings about 10 minutes after it's switched off, and stops with "162 System Options Not Set" until Compaq's SETUP is run again | |

## No longer needed

- **A USB stick:** the Pi Zero W is the GoTEK's stick.
- **A microSD card for the Zero:** it uses the Pi 3's old card.
- **A card-edge adapter:** the floppy cable has two-row plugs.
- **A jumper wire for flashing:** any scrap of wire does.
- **A display and knob for the GoTEK:** the Pi picks the disk.
- **A heatsink and fan for the Pi:** Austin fitted a fan case (by 2026-10-19). Flat out it now peaks
  at 47.8 C without slowing.

## Nice upgrades

| Item | What it gets you | Product | Price |
|---|---|---|---|
| A USB power blocker, only to start DOS from the Zero's "floppy" the moment the Compaq is switched on | Lets the Zero run on its own charger without powering the GoTEK through the data cable. Without it, a Ctrl+Alt+Del a minute after switching on does the same (`zero/README.md`, Power) | Any "USB power blocker" adapter | about $6 to $10 (estimate, not priced) |
| A USB speakerphone for PAL | A proper microphone with echo cancelling: the fix if PAL mishears people. The webcam's microphone is the weak link | [EMEET M0 Plus](https://www.amazon.com/dp/B0BVZLS5GZ) (used in a Pi voice project) or [Jabra Speak 510](https://www.amazon.com/dp/B0FC33QDMX) (one report of it working on a Pi 3B+) | $49.98 or $82.50 |
| A high-endurance microSD for the main Pi | Made for a computer that writes all day. The README has the steps for moving cards | [SanDisk High Endurance 64 GB](https://www.amazon.com/dp/B07P3D6Y5B) | $26.99 |
| A receipt printer | The keepsakes idea: badges, text-art portraits, Zork maps | [Used Epson TM-T88V](https://www.ebay.com/itm/287080386787) (has a cutter) or [POS-5890K](https://www.amazon.com/dp/B0CRR7TWKV). Paper: [80 mm, 10 rolls](https://www.amazon.com/dp/B0FXY3J3H7) | $49.99 or $46.20, paper $18.49 |

## Later, or only if you want it

| Item | When it makes sense | Product | Price |
|---|---|---|---|
| Xircom PE3-10BT pocket Ethernet | You want smoother video than the serial cable gives. An estimated 60 to 90 KB a second through the printer port, against 11.5. It needs new software on both ends | [Used, from Radwell](https://www.ebay.com/itm/318257126034), plus its [12 V adapter](https://www.ebay.com/itm/384998749879) | $89.82 and $42.99, shipped |
| A parallel-port board for the Pi | The cheaper road to the same speed, with more software to write | [Elesar S&P HAT](https://shop.elesar.co.uk/index.php?route=product/product&product_id=76) (ships from the UK) plus a [LapLink cable](https://www.ebay.com/itm/397682843778) | GBP 38.40 plus shipping, $13.95 |
| A 16550A serial chip | Only if PILINK can't hold 115200 on the real Compaq AND its serial chip turns out to sit in a socket | [PC16550DN at Jameco](https://www.jameco.com/z/PC16550DN-Major-Brands-Universal-Asynchronous-Receiver-Transmitter-with-FIFOs-DIP-40_27596.html) | $8.95 |
| A Raspberry Pi 5 | The one thing that would make PAL answer faster: most of its delay is the speech engine on a Pi 3. It means a fresh install | 4 GB board | $70 list in December 2025; about $96 on Amazon in July 2026. Check before buying |
| Compaq's expansion unit, then a PicoMEM card | The fastest road of all (an estimated 200 to 500 KB a second), and the rarest part | The unit turns up on eBay now and then. [PicoMEM](https://texelec.com/product/picomem/) | about $375 to $400, plus $59.99 |
| The lobby toys you liked | A glowing red eye, a big "talk to PAL" button, a motor so the camera follows people | Not priced today | about $10 to $15 each (earlier estimate) |

## Don't buy

- **Anker PowerConf S330:** the one Linux report found calls it useless for a
  voice assistant.
- **A StarTech IDE2CF:** discontinued. The two adapters above replace it.
- **USB-to-printer cables and Zip drives:** neither can link the Compaq to
  the Pi.
- **Anything for 1.44 MB floppies:** this Compaq's ROM and DOS want 1.2 MB,
  and the disk images are built that way.

## Sources

The price and compatibility checks behind this list were made on 13 October
2026. Raspberry Pi 5 prices:
[CNX Software, December 2025](https://www.cnx-software.com/2025-12-01/raspberry-pi-5-1gb-launched-for-45-most-other-pi-4-5-models-get-a-price-increase)
and
[a July 2026 price history](https://dev.to/revenueclaw/raspberry-pi-5-price-history-how-far-have-prices-come-187h).
The clock battery, GoTEK flashing and Compaq storage facts are sourced in
`research_notes/Compaq Portable III faster links/storage_paths.md` and in
[the research report](reports/Compaq%20Portable%20III%20faster%20links.md).
