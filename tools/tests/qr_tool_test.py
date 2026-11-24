# Does PAL's brain reach for the new picture tools when people ask? Calls
# Claude directly (as the pal user, for its key); tools are stand-ins, so
# nothing reaches the screen or the speaker.
import sys, urllib.parse
sys.path.insert(0, "/opt/compaq/pal")
sys.path.insert(1, "/opt/compaq/lib")
import brain, ifixit, pal as palmod
b = brain.Brain(palmod.read_settings(), palmod.read_apps())
joe = {"people": [{"name": "Joe", "pid": "x", "last_seen": 0, "notes": ""}], "strangers": 0, "solo": "x"}

def act(tool, args, *rest):
    print(f"    [tool] {tool} {args}")
    if tool == "find_repair_guides":
        results = [r for r in ifixit.search(str(args.get("search", ""))) if r.get("id")][:3]
        return "Guides: " + "; ".join(
            f"{r['id']}: {r.get('title')} (https://www.ifixit.com/Guide/"
            f"{urllib.parse.quote_plus(str(r.get('title')))}/{r['id']})" for r in results)
    if tool == "show_qr_code":
        return "The QR code for ifixit.com is on the Compaq's screen for a minute: they point their phone's camera at it."
    if tool == "take_photo":
        return ("Took the photo; it's painting onto the Compaq's screen now, a real photo in amber dots, line by "
                "line down the 9600-baud cable like 1987 (about 11 seconds to arrive, then up for half a minute). "
                "It isn't kept unless they ask you to save it (save_photo), and the gallery keeps only a text-art "
                "version, never the photo. You can't see it: joke about the booth or the dots, never how they "
                "look, and don't count down again (the booth did).")
    return "ok"

for script in (["is there a guide for replacing an iPhone 12 battery", "can you send that to my phone"],
               ["take my picture", "can I save it?"],
               ["can your screen show pictures?"]):
    ctx = b.prepare(joe, 3)
    messages = []
    print("---")
    for q in script:
        messages.append({"role": "user", "content": f"Joe says: {q}"})
        text, _ = b.reply(ctx, messages, act)
        messages.append({"role": "assistant", "content": text or "SKIP"})
        print(f"  > {q}\n    {text}")
