import json, sys, time
sys.path.insert(0, "/opt/compaq/pal")
import brain, pal as palmod
settings, apps = palmod.read_settings(), palmod.read_apps()
for model in ("claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"):
    b = brain.Brain(dict(settings, MODEL=model), apps)
    system = b.system(b.situation({"people": [], "strangers": 1}, "spoken", 3))
    msgs = [{"role": "user", "content": "Someone says: tell me a joke about computers"}]
    for thinking in (None, {"type": "disabled"}):
        body_extra = {} if thinking is None else {"thinking": thinking}
        orig = b.call
        def call(system, messages, tools=None, max_tokens=400, extra=body_extra):
            import urllib.request
            body = {"model": b.model, "max_tokens": max_tokens, "system": system, "messages": messages, **extra}
            if tools: body["tools"] = tools
            r = urllib.request.Request(brain.API, data=json.dumps(body).encode(), headers={
                "x-api-key": b.key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
            try:
                return json.load(urllib.request.urlopen(r, timeout=60))
            except urllib.error.HTTPError as e:
                return {"error": e.read().decode()[:200], "content": [], "usage": {}}
        t = time.time(); a = call(system, msgs, b.tools(False))
        kinds = [blk["type"] for blk in a.get("content", [])]
        print(f"{model:18} thinking={'default ' if thinking is None else 'disabled'} {time.time()-t:4.1f} s  "
              f"blocks={kinds} out_tokens={a.get('usage', {}).get('output_tokens')} {a.get('error', '')}")
