"""Write calendar feeds people can subscribe to, so their calendar stays up to date on its own.

  <site>/deadlines.ics   every upcoming funding deadline (Grants.gov + the hand-kept opportunities)
  <site>/conferences.ics every upcoming meeting in conferences.json

Run after funding.py:  python collector/calendar_feeds.py site
"""
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
DOMAIN = "eplas-science.github.io"


def esc(text):
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    """Lines longer than 75 bytes continue on the next line after a space (RFC 5545)."""
    out, raw = [], line.encode("utf-8")
    while len(raw) > 75:
        cut = 75
        while (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = b" " + raw[cut:]
    out.append(raw.decode("utf-8"))
    return "\r\n".join(out)


def calendar(name, about, events):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//EPLAS//Calendar feeds//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{esc(name)}", f"X-WR-CALDESC:{esc(about)}", "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for e in events:
        start = dt.date.fromisoformat(e["start"])
        end = dt.date.fromisoformat(e.get("end") or e["start"]) + dt.timedelta(days=1)
        lines += ["BEGIN:VEVENT", f"UID:{e['uid']}@{DOMAIN}", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{end:%Y%m%d}", f"SUMMARY:{esc(e['title'])}", f"DESCRIPTION:{esc(e['about'])}", f"URL:{e['url']}"]
        if e.get("where"):
            lines.append(f"LOCATION:{esc(e['where'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main(site):
    site = Path(site)
    today = dt.date.today().isoformat()
    deadlines = []
    for f in load(site / "funding.json").get("items", []):
        if f.get("deadline") and f["deadline"] >= today:
            deadlines.append({"uid": f"grant-{f['id']}", "start": f["deadline"], "title": f"Deadline: {f['title']}", "url": f["link"],
                              "about": f"{f.get('agency', '')}\n{f.get('type', '')} · {f.get('stage', '')}\n{f['link']}"})
    for o in load(HERE / "opportunities.json").get("items", []):
        if o.get("deadline") and o["deadline"] >= today:
            note = " (confirm the date on the official page)" if o.get("check") else ""
            deadlines.append({"uid": f"opp-{o['id']}-{o['deadline']}", "start": o["deadline"], "title": f"Deadline: {o['name']}", "url": o["url"],
                              "about": f"{o['org']}\n{o['type']} · {o['stage']}{note}\n{o['url']}"})
    meetings = []
    for m in load(HERE / "conferences.json").get("items", []):
        if m["end"] >= today:
            meetings.append({"uid": m["id"], "start": m["start"], "end": m["end"], "title": m["name"], "url": m["url"],
                             "where": ", ".join(x for x in (m.get("venue"), m.get("city"), m.get("country")) if x), "about": f"{m['org']}\n{m['url']}"})
    deadlines.sort(key=lambda e: e["start"])
    (site / "deadlines.ics").write_text(calendar("EPLAS funding deadlines", "Grant, fellowship, scholarship and award deadlines in Earth and planetary science, from eplas-science.github.io", deadlines), encoding="utf-8", newline="")
    (site / "conferences.ics").write_text(calendar("EPLAS conferences", "Major Earth and planetary science meetings, from eplas-science.github.io", meetings), encoding="utf-8", newline="")
    print(f"calendar feeds: {len(deadlines)} deadlines, {len(meetings)} meetings")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site")
