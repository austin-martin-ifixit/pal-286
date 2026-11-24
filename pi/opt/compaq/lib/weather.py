#!/usr/bin/env python3
"""Current weather and a three-day forecast in plain text, from wttr.in.

Asks for a place (Enter = the last place asked for, or wherever the Pi's
internet connection is) and remembers it for next time, once wttr.in has
found it.
"""

import datetime
import json
try:
    import readline  # noqa: F401  (line editing: an arrow key isn't typed into the place)
except ImportError:
    pass
import os
import urllib.error
import urllib.parse
import urllib.request

SAVED = os.path.expanduser("~/.config/compaq/weather-place")


def ascii(text):
    text = "".join(c for c in str(text) if c >= " " and c != "\x7f")   # no control characters
    return text.encode("ascii", "replace").decode("ascii").strip()


def fetch(place):
    """wttr.in's forecast for place, or None after explaining why not."""
    url = f"https://wttr.in/{urllib.parse.quote(place)}?format=j1"
    request = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        # wttr.in answers an unknown place with a server error.
        print(f"\n  wttr.in couldn't find \"{ascii(place)[:40]}\". Try a city name or ZIP code."
              if place and e.code >= 500 else
              f"\n  The weather service had a problem ({e.code}). Try again later.")
    except ValueError:
        print("\n  The weather service sent something unexpected. Try again later.")
    except Exception as e:
        print(f"\n  Couldn't reach the weather service ({e}).")
    return None


def show(data):
    area = data["nearest_area"][0]
    now = data["current_condition"][0]
    print(f"\n  {ascii(area['areaName'][0]['value'])}, {ascii(area['region'][0]['value'])}".upper())
    # (everything the service sends is cleaned: only plain text reaches the screen)
    print(f"\n  Now:  {ascii(now['weatherDesc'][0]['value'])}, {ascii(now['temp_F'])[:5]} F "
          f"(feels like {ascii(now['FeelsLikeF'])[:5]} F)")
    print(f"        Wind {ascii(now['windspeedMiles'])[:5]} mph {ascii(now['winddir16Point'])[:5]}, "
          f"humidity {ascii(now['humidity'])[:5]}%\n")
    for day in data["weather"]:
        date = datetime.date.fromisoformat(day["date"]).strftime("%a %b %d")
        midday = ascii(day["hourly"][len(day["hourly"]) // 2]["weatherDesc"][0]["value"])
        rain = max(int(hour["chanceofrain"]) for hour in day["hourly"])
        print(f"  {date:<11} {ascii(day['mintempF'])[:4]:>3} to {ascii(day['maxtempF'])[:4]:>3} F   "
              f"{midday[:32]:<32} rain {rain:>3}%")


def main():
    try:
        with open(SAVED) as f:
            last = f.read().strip()
    except OSError:
        last = ""

    print("\n  WEATHER\n")
    place = input(f"  Place (Enter for {last or 'here'}): ").strip() or last
    data = fetch(place)
    if data is None:
        return
    try:
        show(data)
    except (KeyError, IndexError, TypeError, ValueError):
        print("\n  The weather service sent something unexpected. Try again later.")
        return
    if place and place != last:
        try:
            os.makedirs(os.path.dirname(SAVED), exist_ok=True)
            with open(SAVED, "w") as f:
                f.write(place + "\n")
        except OSError:
            pass                     # (not remembered for next time: no matter)


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        pass
    try:
        input("\n  Press Enter to return to the menu. ")
    except (EOFError, KeyboardInterrupt):
        pass
