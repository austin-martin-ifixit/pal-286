# Opens a web address in Lynx, set up for the Compaq: plain ASCII, no colour,
# and cookies switched off so sites don't stop to ask about them.
# Source it, then: browse URL
browse() {
  exec lynx -cookies -nocolor -display_charset=us-ascii "$1"
}

# urlencode TEXT: TEXT made safe to put in a web address.
urlencode() {
  python3 -c 'import sys, urllib.parse; print(urllib.parse.quote_plus(sys.argv[1]))' "$1"
}

LYNX_TIPS=(
  "Up and Down move between links, Right or Enter follows one, Left goes back."
  "Space shows the next page, b the one before. g goes to an address, Q quits."
)
