"""Client for the FixBot Partner API (https://app.fixbot.pro/api-docs).

Search and guide lookups are open. Plans need a FixBot API key, created by a
workspace admin at https://app.fixbot.pro/workspace/settings/api-keys, and
an active FixBot Pro or Enterprise subscription.
"""

import html
import http.client
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://app.fixbot.pro"
# The PAL simulator's stand-in FixBot (tools/tests/fixbot_sim_test.py) is the
# only other server allowed, and only on this machine.
if re.fullmatch(r"http://127\.0\.0\.1:\d{2,5}", os.environ.get("FIXBOT_BASE", "")):
    BASE = os.environ["FIXBOT_BASE"]
PLAN_TIMEOUT = 300   # plans "take a minute or two"

# What each failure means for someone sitting at the Compaq.
STATUS_MESSAGES = {
    401: "FixBot didn't accept the API key. It may have expired or been revoked; "
         "set a new one with set-fixbot-key.sh.",
    402: "The FixBot workspace's subscription isn't active, so plans are paused.",
    403: "This API key doesn't have access to FixBot plans.",
    404: "FixBot couldn't find this conversation. Type new to start a fresh one.",
    413: "That was too much text for FixBot. Try a shorter description.",
    421: "This key belongs to a different FixBot server.",
}


class FixBotError(Exception):
    """A request failed. The message is written for the person at the Compaq."""


def _request(path, body=None, key=None, timeout=60, not_found=None):
    headers = {"Accept": "application/json", "User-Agent": "compaq-link/1.0"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(BASE + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        if e.code == 404 and not_found:
            raise FixBotError(not_found) from e
        if e.code in STATUS_MESSAGES:
            raise FixBotError(STATUS_MESSAGES[e.code]) from e
        if e.code >= 500:
            raise FixBotError(f"FixBot had a problem on its end ({e.code}). Try again.") from e
        raise FixBotError(f"FixBot rejected the request ({e.code}): {_error_text(e)}") from e
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as e:
        raise FixBotError(f"Couldn't reach FixBot. Is the Pi online? ({e})") from e
    except ValueError as e:  # not JSON: a Wi-Fi sign-in page or a proxy answered
        raise FixBotError("Got an unexpected answer instead of FixBot. Is the Pi's "
                          "Wi-Fi asking for a sign-in?") from e


def _error_text(e):
    try:
        body = json.load(e)
    except (ValueError, OSError, http.client.HTTPException):
        return "no details"
    if not isinstance(body, dict):
        return "no details"
    return body.get("message") or body.get("reason") or body.get("error") or "no details"


def check_key(key):
    """Raises FixBotError unless key is accepted. Costs no plan: an empty
    request passes the key check, then fails validation with 400."""
    try:
        _request("/api/plan/repair", {}, key)
    except FixBotError as e:
        if isinstance(e.__cause__, urllib.error.HTTPError) and e.__cause__.code == 400:
            return
        raise


def plan(key, device, symptoms, chatid=None, kind="repair", audience="consumer"):
    """A repair (or test) plan. Pass the previous chatid to refine it."""
    body = {"device": {"model": device}, "audience": audience,
            "context": {"symptoms": symptoms}}
    if chatid:
        body["chatid"] = chatid
    return _request(f"/api/plan/{kind}", body, key, timeout=PLAN_TIMEOUT)


def plan_text(result):
    """A plan response as Markdown: the plan, its guide, then its parts."""
    text = result.get("plan", "")
    guide = result.get("primaryGuide")
    if guide:
        text += f"\n\n**Guide:** {guide['title']}\n{guide['url']}"
    parts = result.get("partsEstimate") or []
    if parts:
        text += "\n\n**Parts:**"
        for part in parts:
            price = ""
            if part.get("cost") is not None:
                price = f" - {part['cost']:.2f} {part.get('currency', '')}".rstrip()
            text += f"\n- {part['name']}{price}"
    return text


def search(query, doc_types="guide"):
    params = urllib.parse.urlencode({"q": query, "docTypes": doc_types})
    found = _request(f"/api/search?{params}")
    results = found.get("results") if isinstance(found, dict) else None
    return results if isinstance(results, list) else []


def guide(guide_id):
    return _request(f"/api/resources/guide/{urllib.parse.quote(str(guide_id))}",
                    not_found="iFixit couldn't find that guide any more.")


def strip_html(text):
    text = re.sub(r"<br\s*/?>|</p>\s*<p>", "\n", text or "")
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


BULLET_LABELS = {"icon_caution": "CAUTION: ", "icon_note": "Note: ",
                 "icon_reminder": "Reminder: "}


def guide_overview(g):
    """A guide's title, facts, tools, parts and introduction, as Markdown."""
    out = [f"# {g['title']}", ""]
    facts = [f"Difficulty: {g['difficulty']}" if g.get("difficulty") else "",
             f"Time: {g['time_required']}" if g.get("time_required") else ""]
    if any(facts):
        out += [". ".join(f for f in facts if f) + ".", ""]
    for label, key in (("Tools", "tools"), ("Parts", "parts")):
        items = [i["text"] for i in g.get(key) or [] if i.get("text")]
        if items:
            out += [f"{label}: " + ", ".join(items), ""]
    intro = strip_html(g.get("introduction"))
    if intro:
        out.append(intro)
    return "\n".join(out)


def step_text(step, steps):
    """One step of a guide (of steps), as Markdown."""
    title = step.get("title") or ""
    out = [f"## Step {step.get('number', '')} of {steps}" + (f": {title}" if title else ""), ""]
    for line in step.get("lines") or []:
        indent = "  " * int(line.get("level") or 0)
        label = BULLET_LABELS.get(line.get("bullet"), "")
        out.append(f"{indent}- {label}{strip_html(line.get('text_rendered'))}")
    return "\n".join(out)


def step_photos(step):
    """The web addresses of a step's photos."""
    media = step.get("media") or {}
    if not isinstance(media, dict) or media.get("type") != "image":
        return []
    return [m["medium"] for m in media.get("data") or []
            if isinstance(m, dict) and str(m.get("medium", "")).startswith("https://")]
