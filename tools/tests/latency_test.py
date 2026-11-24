# After the speed work: when would PAL start talking? Runs as pal on the Pi.
import subprocess, sys, time, re
sys.path.insert(0, "/opt/compaq/pal")
import brain, pal as palmod, senses
settings, apps = palmod.read_settings(), palmod.read_apps()
ears, voice = senses.Ears(), senses.Voice()
present = {"people": [], "strangers": 1}
questions = [
             "Hey pal, who won the Yankees game last night?"]
for q in questions:
    raw = subprocess.run(["espeak-ng", "-v", "en-us+m1", "-s", "160", "--stdout", q], capture_output=True).stdout
    pcm = subprocess.run(["sox", "-t", "wav", "-", "-r", "16000", "-c", "1", "-b", "16", "-t", "raw", "-"], input=raw, capture_output=True).stdout
    t = time.time(); heard = ears.transcribe(pcm); t_whisper = time.time() - t
    print(f"\n{q}\n  understanding the question: {t_whisper:.1f} s")
    for model in ("claude-sonnet-5-5",):
        b = brain.Brain(dict(settings, MODEL=model), apps)
        first = {}
        sentences = palmod.Sentences(lambda s: first.setdefault("t", time.time()) and first.setdefault("s", s))
        t = time.time()
        text, _ = b.reply(b.prepare(present, 3), [{"role": "user", "content": "Someone says: " + heard}],
                          lambda *a: "Opened it on the Compaq's screen.", on_text=sentences.add)
        sentences.flush(); total = time.time() - t
        t1 = first.get("t", time.time()) - t
        t_r = time.time(); voice.render(first.get("s", "x")); t_render = time.time() - t_r
        print(f"  {model:18} starts talking after {t1 + t_render:4.1f} s (all written {total:4.1f} s, {len(text.split())} words): "
              f"{first.get('s', '')[:70]!r}")
