COMPAQ - RASPBERRY PI LINK DISK

PI.BAT         Connects to the Pi. Start here.
PILINK.COM     The Pi's direct line to this screen and keyboard: text,
               photos, video and Doom, as fast as the cable goes (up to
               115200 baud).
KERMIT.EXE     MS-DOS Kermit 3.16 (free and open source, kermitproject.org):
               file transfers, and the old way to connect.
MSKERMIT.INI   Kermit's settings for connecting: COM1, 9600 baud, VT102.
SERVE.INI      Kermit's settings for a file transfer the Pi asked for.
INSTALL.BAT    Copies this disk to the hard disk and starts there in the Pi.

TO CONNECT TO THE PI
  A:\> PI
  The Pi's shared screen appears: the same one people see at
  http://compaq.local on the office network. Press Enter for the menu.
  "Waiting for the Raspberry Pi" for more than half a minute means the
  cable or the Pi isn't there.

KEYS
  F10              back to the Pi's main menu, from any program
  Ctrl+Alt+Esc     leave the Pi, back to DOS (type PI to go back)

FILE TRANSFERS
  From the Pi's menu: Transfer files with the Compaq. The screen goes to
  Kermit for the transfer and comes back to the Pi by itself. Files
  arrive in the folder PI was started from.

THE OLD WAY: KERMIT
  A:\> KERMIT connects through Kermit, a VT102 terminal at 9600 baud.
  Photos and video still work (Kermit starts PILINK for them, which needs
  DOS's COMMAND.COM where DOS expects it: on the disk you booted from).
  Ctrl-] then C    Kermit's prompt
  CONNECT          back to the Pi screen
  EXIT             back to DOS

TO INSTALL ON THE HARD DISK
  C:\> A:INSTALL
  It copies this disk to C:\PI and, if C:\AUTOEXEC.BAT isn't there yet,
  makes one that starts in the Pi every time the Compaq boots. If it is
  there, add C:\PI to its PATH line (PI finds PILINK, Kermit and its
  settings along the PATH) and PI as its last line.
