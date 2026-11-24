import sys
sys.path.insert(0, "/opt/compaq/pal")
import brain, pal as palmod
b = brain.Brain(palmod.read_settings(), palmod.read_apps())
joe = {"people": [{"name": "Joe", "pid": "x", "last_seen": 0, "notes": "Fixing an iPhone 12 battery; likes DUSTRUN."}],
       "strangers": 0, "solo": "x"}
print("GREETINGS")
for i in range(8):
    ctx = b.prepare(joe, 3)
    text = b.greet(ctx, b.greeting_ask(["Joe"], 0))
    b.note(text)
    print(f" {i+1:2}. {text}")
print("CHAT")
ctx = b.prepare(joe, 10)
messages = []
for q in ["what's up pal", "ugh I have three meetings tomorrow", "tell me a joke", "my phone is at 2 percent", "how much memory do you have", "ok I gotta get back to work"]:
    messages.append({"role": "user", "content": f"Joe says: {q}"})
    text, _ = b.reply(ctx, messages, lambda *a: "ok")
    b.note(text)
    print(f"  > {q}\n    {text}")
