#!/bin/bash
# Downloads the free DOS classics for the Compaq's disks to ~/build/dos on
# the Pi, checks each against its pinned SHA-256, and unpacks each into its
# own folder. Only software its owners made free (freeware, MIT, GPL, a
# published free license, or free for personal use) is listed.
# Run from the Mac:  ssh pizero 'bash -s' < fetch-dos.sh
# Zork's story files come from fetch-games.sh. MS-DOS Kermit goes to
# ~/build/msk316 (where make-disks.sh looks for it).
set -euo pipefail
base=~/build/dos
wayback=https://web.archive.org/web

get() {  # get NAME SHA256 URL: download, verify, unpack into NAME/files
  local name=$1 sum=$2 url=$3 file
  file="$base/$name/download/${url##*/}"
  mkdir -p "$base/$name/download"
  [ -s "$file" ] || curl -fsSL --retry 2 -m 300 -o "$file" "$url"
  if ! echo "$sum  $file" | sha256sum --check --status; then
    echo "  $name: checksum mismatch, removed. The file at $url has changed." >&2
    rm -f "$file"
    return 1
  fi
  [ -d "$base/$name/files" ] || python3 -I -c \
    'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' \
    "$file" "$base/$name/files"
  printf "  %-10s %9s bytes, checksum OK\n" "$name" "$(stat -c %s "$file")"
}

# Microsoft, free since 1999, from Microsoft's own server.
get word55 0bcc30dc4e7b48e714178e0e6c87d392c51d5b71079f7a7e319602b26f239113 \
  https://download.microsoft.com/download/word97win/Wd55_be/97/WIN98/EN-US/Wd55_ben.exe
# Frotz 2.55 for 16-bit DOS (GPL), from the IF Archive.
get frotz 08f4102752f3e0db26d0b61fc8ff62e18a00f6d37eba46f5bd02bf676165f153 \
  https://www.ifarchive.org/if-archive/infocom/interpreters/frotz/frotz255.zip
# ZZT, freeware since 1997, from the Museum of ZZT.
get zzt fdf5a0f9f45c32447199aaad3d3caa5dbabcb6ec6a5f55cd954d060515488d5e \
  https://museumofzzt.com/zgames/z/zzt.zip
# Apogee's freeware releases (3D Realms, 2009), archived from ftp.3drealms.com.
get kroz 478ae1a74a8e77420b9aae74581825f3784d9fc6f2fee6185567935fb537a245 \
  "$wayback/20201123055138id_/ftp://ftp.3drealms.com/freeware/krozfree.zip"
get supernova e6593841ade60e7b0f4d075be28db73b45e62a6600865a0a3ecad1038fe3a257 \
  "$wayback/20201123055120id_/ftp://ftp.3drealms.com/freeware/snova_fw.zip"
get titanic 1dc82be77b92cca1cff8f30fe54d639651cdf2b95e3e70f306c8f03e5e3dad66 \
  "$wayback/20201123055123id_/ftp://ftp.3drealms.com/freeware/tit_free.zip"
# Digger Remastered (GPL), from digger.org.
get digger 378c315a5e8ca39a0c0528d16846dfa157bfa9f4f92583fc7be08dd3522c81a0 \
  https://www.digger.org/digger.zip
# As-Easy-As 5.7, free license published by TRIUS in 2011 (no https there).
get asa 4a92a476294a4624836ee45e72a364865cdd2531eb062bde4487b0d1419ff315 \
  http://www.triusinc.com/old_files/asa57.exe
# GW-BASIC rebuilt from Microsoft's MIT-licensed source by TK Chia.
get gwbasic 077e4b36c079fecbd127cc85a01ce6b4d6ad9e8546c7e6a6d43e5c3a37243d6b \
  https://gitlab.com/-/project/18940548/uploads/7b2a0d5578bab4b66780079a45d3d25d/GWB26A05.ZIP
# Personal-use-only freebies (no sharing copies): VisiCalc from Dan Bricklin's
# site with Lotus's permission (no working https there); Turbo Pascal 5.5 and
# Turbo C 2.01 from Embarcadero's "Antique Software" museum.
get visicalc c346d6b166389ea6e7967bd4e804578c3cd0a4d58e8149ba02fde0a5eb32391e \
  http://www.bricklin.com/anonymous/visicalc-executable.zip
get tp55 a04ff65555f88cd7714a11362c6f625f254932679ad5623b207015893ef638b6 \
  https://altd.embarcadero.com/download/museum/tp55.zip
get tc201 2c87f988605ae9ed70e5fef35b9854de87e36ccdb021caec35ab2424ca4b5553 \
  https://altd.embarcadero.com/download/museum/tc201.zip

# Doom8088: Doom for 16-bit PCs like this 286 (GPL, github.com/FrenkelS/Doom8088),
# the CGA versions, with Doom's shareware first episode already prepared.
get doom8088 4d3517addae04c2b18f9665397bcf401e9078dfb64caab2540fe34d3d59f70b0 \
  https://github.com/FrenkelS/Doom8088/releases/download/v20260304/DOOM8088-CGA-v20260304.zip

# FreeDOS 1.3 (GPL), the floppy edition, from the FreeDOS project's own
# mirror: its 1.2 MB boot disk gives the boot disk its boot sector, kernel
# and COMMAND.COM (tools/build_disks.py, boot_disk).
get freedos 75a4e11a7fce6f124e20927b3022b4b715a2a3f7324c5f5bfea42d90d80eb072 \
  https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/distributions/1.3/official/FD13-FloppyEdition.zip

# Compaq's own User Diagnostics 5.08 and SETUP 5.05 (January 1988), the
# diskette Compaq gave away for its 286 and 386 machines (SETUP sets the
# CMOS: the hard disk's type, the drives, the memory). From the PCjs archive,
# in its JSON disk format; build_disks.py turns it back into a disk.
mkdir -p "$base/compaq-diag"
diag="$base/compaq-diag/COMPAQ-DIAGS-508-012988-REVK.json"
[ -s "$diag" ] || curl -fsSL --retry 2 -m 300 -o "$diag" \
  https://diskettes.pcjs.org/pcx86/diag/compaq/5.08/COMPAQ-DIAGS-508-012988-REVK.json
if echo "ceb3fa03ece79f645bc443fe2eb6cc7dd5dfb09054104803f80949a1a5718e11  $diag" | sha256sum --check --status; then
  printf "  %-10s %9s bytes, checksum OK\n" compaq-diag "$(stat -c %s "$diag")"
else
  echo "  compaq-diag: checksum mismatch, removed." >&2; rm -f "$diag"
fi

# MS-DOS Kermit 3.16 (free and open source, the Kermit Project), for the
# Compaq's link disk.
base=~/build get msk316 de77fdadfb23c00deced62706481807eaa8c230d6f1fdec51582f35b8f10bb36 \
  https://www.kermitproject.org/msdoskermit/msk316.zip
