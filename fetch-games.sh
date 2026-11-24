#!/bin/bash
# Downloads the text adventures for the Text adventures menu into
# /var/lib/compaq/games on the Pi, which deploys leave alone.
# Run from the Mac:  ssh pizero 'sudo bash -s' < fetch-games.sh
#
# Zork I-III: Microsoft's MIT-licensed release (Nov 2025), compiled story
#   files from the historicalsource repositories.
# The rest: freeware, from the IF Archive.
set -euo pipefail

games=/var/lib/compaq/games
install -d -m 755 "$games"

# Each file's SHA-256, checked after download: a changed or damaged file is
# refused rather than installed.
declare -A sum=(
  [zork1.z3]=37084966477dff679282de42974b2077156b1bd68fad92a65d4ea94d8eb64d79
  [zork2.z3]=3ae7d5558943e9721f3e4b273c8a7faec1a03a604e1ae4ee1cde472c21cb24ac
  [zork3.z3]=b637a242865d059890184164ce8dec28554cc80901dcbf26c740b2d1ed0d4eb8
  [curses.z5]=330100bf1c1ab8ed64065ceb58145ebb87cb6faef5b331fbc6684be4f14fe7da
  [Tangle.z5]=dd5b510fb04daaa2fa9a40fc94414eee3719a72e274c77288b41629e32470817
  [photopia.z5]=ba14a14dfdede4b7ad97846c13ca0ea07048334ac767649d9aa84add7fae20a5
  [905.z5]=0f41ff7811668e236060b399ced1cd0481c1bb624a8876fc7e16dc58816f1ecb
  [LostPig.z8]=7bffe25e933aa22a2b1e9bfc8073bee5687d79a70394da19e50bfed5755368c4
  [Advent.z5]=6179b5d5b17d692ec83fe64101ff8e4092390166c2b05063e7310eb976b93ea0
  [dreamhold.z8]=399dbfb92024d2a702029dd1921a1023569888941683d953d3755d6856ce2941
)

fetch() {  # fetch URL FILE
  if [ ! -s "$games/$2" ]; then
    curl -fsSL --retry 2 -o "$games/$2.part" "$1"
    if ! echo "${sum[$2]}  $games/$2.part" | sha256sum -c --quiet 2>/dev/null; then
      rm -f "$games/$2.part"
      echo "  $2 didn't match its checksum; skipped." >&2
      return
    fi
    mv "$games/$2.part" "$games/$2"
  fi
  printf "  %-14s %8s bytes\n" "$2" "$(stat -c %s "$games/$2")"
}

zork=https://raw.githubusercontent.com/historicalsource
fetch "$zork/zork1/master/COMPILED/zork1.z3" zork1.z3
fetch "$zork/zork2/master/COMPILED/zork2.z3" zork2.z3
fetch "$zork/zork3/master/COMPILED/zork3.z3" zork3.z3

ifarchive=https://www.ifarchive.org/if-archive/games/zcode
for f in curses.z5 Tangle.z5 photopia.z5 905.z5 LostPig.z8 Advent.z5 dreamhold.z8; do
  fetch "$ifarchive/$f" "$f"
done

chmod 644 "$games"/*
