"""Build one .ics file per event in the index.html schedule and link each event row to it.

Run from the repo root after editing the schedule:

    python tools/make_ics.py

Rewrites cal/*.ics (removing files for events that no longer exist) and refreshes the
add-to-calendar button on every .ev row in index.html. Safe to run repeatedly.
"""
import os, re, sys, html, hashlib
from datetime import datetime, timedelta

src = sys.argv[1] if len(sys.argv) > 1 else "index.html"
outdir = sys.argv[2] if len(sys.argv) > 2 else "cal"
text = open(src, encoding="utf-8").read()
sched = text[text.index('<section id="schedule">'):text.index('<!-- ============ SEMINARS')]

VENUE = "York Expo Center, 334 Carlisle Ave, York, PA 17404"
STAMP = "20261023T000000Z"


def strip(s):
    s = re.sub(r"</span> <span", "</span>, <span", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def parse_t(s):
    s = s.strip().lower()
    if s == "noon" or s == "12:00 noon":
        return 12, 0, "pm"
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?:\s*(am|pm))?", s)
    if not m:
        raise ValueError(s)
    return int(m[1]), int(m[2]), m[3]


def to24(h, mi, ap):
    if ap == "pm" and h != 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return h, mi


def parse_range(t):
    t = t.strip().lower()
    late = False
    if t.endswith("until late"):
        t, late = t[: -len("until late")].strip(), True
    if t == "12:00 noon":
        return (12, 0), None, late
    parts = t.split("-")
    sh, sm, sap = parse_t(parts[0])
    if len(parts) == 1:
        return to24(sh, sm, sap), None, late
    eh, em, eap = parse_t(parts[1])
    if sap is None:
        sap = eap
        if eap == "pm" and sh != 12 and sh > eh:
            sap = "am"
    return to24(sh, sm, sap), to24(eh, em, eap), late


def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    outl, cur = [], b""
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > (75 if not outl else 74):
            outl.append(cur.decode("utf-8"))
            cur = b""
        cur += cb
    outl.append(cur.decode("utf-8"))
    return "\r\n ".join(outl)


HEADER = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//ccmftrains//Clem's York Primer Fall 2026//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "BEGIN:VTIMEZONE",
    "TZID:America/New_York",
    "BEGIN:DAYLIGHT",
    "TZOFFSETFROM:-0500",
    "TZOFFSETTO:-0400",
    "TZNAME:EDT",
    "DTSTART:19700308T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
    "END:DAYLIGHT",
    "BEGIN:STANDARD",
    "TZOFFSETFROM:-0400",
    "TZOFFSETTO:-0500",
    "TZNAME:EST",
    "DTSTART:19701101T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
    "END:STANDARD",
    "END:VTIMEZONE",
]

KIND = {"show": "Show", "talk": "Seminar", "meet": "Meeting", "social": "Social", "away": "Off-site"}
count = 0
files, links = {}, {}
for day in re.finditer(r'<div class="day" id="(\w+)" data-date="(\d{4}-\d{2}-\d{2})">(.*?)\n  </div>', sched, re.S):
    date = datetime.strptime(day[2], "%Y-%m-%d")
    for ev in re.finditer(r'<div class="ev[^"]*" data-k="(\w+)"><div class="t">(.*?)</div><div>(.*?)</div>(?:<a class="ev-cal"[^>]*></a>)?</div>(?=[ \t]*$)', day[3], re.M):
        kind, t, body = ev[1], strip(ev[2]), ev[3]
        title = strip(re.search(r'<span class="w">(.*?)</span>', body)[1])
        dm = re.search(r'<div class="d">(.*)</div>', body)
        detail = strip(dm[1]) if dm else ""
        (sh, sm), end, late = parse_range(t)
        start = date.replace(hour=sh, minute=sm)
        if end:
            stop = date.replace(hour=end[0], minute=end[1])
        elif late:
            stop = date.replace(hour=23, minute=0)
        else:
            stop = start + timedelta(minutes=15 if kind == "show" else 60)
        if kind == "away":
            loc = detail.split(". ")[0] if detail else ""
        else:
            place = detail.split(". ")[0].split(" · ")[0].rstrip(".")
            place = re.sub(r", (playing|courtesy) .*$", "", place)
            if re.search(r"Hall|Room|Lobby|Promenade|Gate", place) and "badge" not in place.lower():
                loc = f"{place}, {VENUE}"
            else:
                loc = VENUE
        desc = f"{KIND[kind]} · {t}"
        if detail:
            desc += f"\n{detail}"
        desc += "\nTimes and places subject to change. https://clem2026.ccmftrains.com/#" + day[1]
        uid = hashlib.sha1(f"{day[2]}|{t}|{title}".encode()).hexdigest()[:16]
        lines = HEADER + [
            "BEGIN:VEVENT",
            f"UID:{uid}@clem2026.ccmftrains.com",
            f"DTSTAMP:{STAMP}",
            f"DTSTART;TZID=America/New_York:{start:%Y%m%dT%H%M%S}",
            f"DTEND;TZID=America/New_York:{stop:%Y%m%dT%H%M%S}",
            f"SUMMARY:{esc(title)}",
            f"LOCATION:{esc(loc)}",
            f"DESCRIPTION:{esc(desc)}",
            f"CATEGORIES:{KIND[kind]}",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        if len(slug) > 48:
            slug = slug[:49].rsplit("-", 1)[0]
        name = f"{day[1]}-{start:%H%M}-{slug}.ics"
        assert name not in files, name
        files[name] = lines
        links[ev.start()+day.start(3)] = (ev[0], name, title)
        count += 1

os.makedirs(outdir, exist_ok=True)
for old in os.listdir(outdir):
    if old.endswith(".ics") and old not in files:
        os.remove(os.path.join(outdir, old))
for name, lines in files.items():
    with open(os.path.join(outdir, name), "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(fold(l) for l in lines) + "\r\n")

rel = os.path.basename(os.path.normpath(outdir))
new_sched = sched
for pos in sorted(links, reverse=True):
    raw, name, title = links[pos]
    clean = re.sub(r'<a class="ev-cal"[^>]*></a>', "", raw)
    a = f'<a class="ev-cal" href="{rel}/{name}" type="text/calendar" title="Add to calendar" aria-label="Add {html.escape(title)} to your calendar"></a>'
    new_sched = new_sched[:pos] + clean[:-len("</div>")] + a + "</div>" + new_sched[pos + len(raw):]
with open(src, "w", encoding="utf-8", newline="") as f:
    f.write(text.replace(sched, new_sched, 1))
print(count, "events")
