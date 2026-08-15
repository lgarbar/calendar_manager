#!/usr/bin/env python3
"""Class Schedule Converter V2.

Accepts schedule text files, saved HTML pages, or pasted schedule text; extracts
course meetings; lets the user review/edit them; and creates a portable .ics
calendar for Apple Calendar, Google Calendar, and Outlook.

No third-party Python packages are required.
"""
from __future__ import annotations
import argparse, html, re, sys, uuid, webbrowser
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

COURSE_RE = re.compile(r"^([A-Z][A-Z0-9-]*\s+\d+[A-Z]?)\s*:\s*(.+?)\s*$")
TIME_RE = re.compile(r"^(\d{1,2}:\d{2}\s*[ap](?:m)?)\s*-\s*(\d{1,2}:\d{2}\s*[ap](?:m)?)$", re.I)
DAY_RE = re.compile(r"^[MTWRF]+$")
DAY_TO_ICAL = {"M":"MO","T":"TU","W":"WE","R":"TH","F":"FR"}
DAY_TO_WEEKDAY = {"M":0,"T":1,"W":2,"R":3,"F":4}

@dataclass
class ClassMeeting:
    course_code: str
    course_title: str
    days: list[str]
    start_time: Optional[time]
    end_time: Optional[time]
    location: Optional[str]
    enabled: bool = True
    @property
    def schedulable(self): return self.enabled and bool(self.days and self.start_time and self.end_time)

class VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in {"script","style","noscript"}: self.skip += 1
        elif not self.skip and tag in {"br","p","div","tr","td","th","li","section","article","h1","h2","h3","h4"}: self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in {"script","style","noscript"} and self.skip: self.skip -= 1
        elif not self.skip and tag in {"p","div","tr","td","th","li","section","article","h1","h2","h3","h4"}: self.parts.append("\n")
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)

class EnrolledScheduleParser(HTMLParser):
    """Extract only the rendered Vanderbilt enrolled-classes container."""
    def __init__(self):
        super().__init__(); self.parts=[]; self.depth=0; self.active=False; self.skip=0; self.found=False
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if not self.active and tag == "div" and attrs.get("id") == "enrolledClassSections_content":
            self.active=True; self.found=True; self.depth=1; return
        if self.active:
            if tag == "div": self.depth += 1
            if tag in {"script","style","noscript"}: self.skip += 1
            elif not self.skip and tag in {"br","p","div","tr","td","th","li","section","article","h1","h2","h3","h4","span","table"}: self.parts.append("\n")
    def handle_endtag(self, tag):
        if not self.active: return
        if tag in {"script","style","noscript"} and self.skip:
            self.skip -= 1
        elif not self.skip and tag in {"p","div","tr","td","th","li","section","article","h1","h2","h3","h4","span","table"}:
            self.parts.append("\n")
        if tag == "div":
            self.depth -= 1
            if self.depth == 0: self.active=False
    def handle_data(self, data):
        if self.active and not self.skip: self.parts.append(data)

def html_to_text(raw):
    # Vanderbilt's schedule shell is huge and contains many unrelated course-like
    # strings. If the enrolled schedule has been serialized into the HTML, scope
    # parsing to that container. Otherwise fall back for ordinary HTML pages.
    if "enrolledClassSections_content" in raw:
        p=EnrolledScheduleParser(); p.feed(raw)
        scoped=html.unescape("".join(p.parts))
        # Rendered Vanderbilt HTML stores the course code and title in adjacent
        # spans, so generic visible-text extraction puts them on separate lines.
        # Recombine those lines into the same CODE: Title shape used by the text parser.
        lines=clean_lines(scoped)
        rebuilt=[]; i=0
        while i < len(lines):
            if re.fullmatch(r"[A-Z][A-Z0-9-]*\s+\d+[A-Z]?:", lines[i]) and i+1 < len(lines):
                rebuilt.append(lines[i] + " " + lines[i+1]); i += 2
            else:
                rebuilt.append(lines[i]); i += 1
        scoped="\n".join(rebuilt)
        if clean_lines(scoped): return scoped
        raise ValueError(
            "This Vanderbilt HTML contains the schedule container, but the container is empty. "
            "The enrolled classes are loaded later by JavaScript/AJAX and are not present in this saved file. "
            "Use copied schedule text, or save/export the rendered DOM after the classes are visible."
        )
    p=VisibleTextParser(); p.feed(raw); return html.unescape("".join(p.parts))

def parse_clock(value):
    cleaned=re.sub(r"\s+","",value.lower()).replace("a","am").replace("p","pm").replace("amm","am").replace("pmm","pm")
    return datetime.strptime(cleaned,"%I:%M%p").time()

def parse_user_clock(value):
    value=value.strip()
    for fmt in ("%I:%M %p","%I:%M%p","%H:%M"):
        try: return datetime.strptime(value.upper(),fmt).time()
        except ValueError: pass
    raise ValueError("Use a time such as 10:00 AM, 1:15 PM, or 13:15")

def clean_lines(text): return [re.sub(r"\s+"," ",x).strip() for x in text.splitlines() if x.strip()]

def split_blocks(lines):
    out=[]; cur=[]
    for line in lines:
        if COURSE_RE.match(line):
            if cur: out.append(cur)
            cur=[line]
        elif cur: cur.append(line)
    if cur: out.append(cur)
    return out

def parse_block(block):
    m=COURSE_RE.match(block[0]); code,title=m.groups()
    days=[]; start=end=None; loc=None; ti=None
    for i,line in enumerate(block[1:],1):
        tokens=line.upper().split()
        if tokens and DAY_RE.fullmatch(tokens[-1]): days=list(tokens[-1])
        tm=TIME_RE.match(line)
        if tm: start,end=parse_clock(tm.group(1)),parse_clock(tm.group(2)); ti=i; break
    if ti is not None and ti+1 < len(block):
        candidate=block[ti+1]
        if candidate.upper() != "TBA" and not candidate.lower().startswith("note:"): loc=candidate
    return ClassMeeting(code,title,days,start,end,loc, start is not None and end is not None and bool(days))

def parse_text(text): return [parse_block(b) for b in split_blocks(clean_lines(text))]

def load_input(path):
    raw=path.read_text(encoding="utf-8-sig",errors="replace")
    if path.suffix.lower() in {".html",".htm"} or re.search(r"<html|<body|<table|<div",raw,re.I):
        try: raw=html_to_text(raw)
        except ValueError as ex: raise SystemExit(str(ex))
    return raw

def fmt_time(t): return t.strftime("%I:%M %p").lstrip("0") if t else "TBA"
def describe(c): return f"{c.course_code} - {c.course_title} | {''.join(c.days) or 'TBA'} | {fmt_time(c.start_time)} - {fmt_time(c.end_time)} | {c.location or 'TBA'}"

def preview(classes):
    print("\nClasses:\n")
    for i,c in enumerate(classes,1): print(f"{i}. [{'x' if c.schedulable else ' '}] {describe(c)}")
    print()

def ask(prompt, default=None):
    suffix=f" [{default}]" if default not in (None,"") else ""
    v=input(prompt+suffix+": ").strip(); return v if v else default

def edit_class(c):
    print("\nPress Enter to keep each value.")
    c.course_code=ask("Course code",c.course_code); c.course_title=ask("Course title",c.course_title)
    while True:
        d=ask("Days (M T W R F; e.g. MW or TR)","".join(c.days)).upper().replace(" ","")
        if d and DAY_RE.fullmatch(d): c.days=list(d); break
        if not d: c.days=[]; break
        print("Use only M, T, W, R, F (R = Thursday).")
    try:
        s=ask("Start time",fmt_time(c.start_time) if c.start_time else "")
        e=ask("End time",fmt_time(c.end_time) if c.end_time else "")
        c.start_time=parse_user_clock(s) if s else None; c.end_time=parse_user_clock(e) if e else None
    except ValueError as ex: print(ex); return edit_class(c)
    c.location=ask("Location",c.location or "") or None
    c.enabled=bool(c.days and c.start_time and c.end_time)

def review(classes):
    while True:
        preview(classes)
        cmd=input("Review: [Enter] continue, number edit, d NUMBER disable, a add, q quit: ").strip().lower()
        if not cmd: return
        if cmd=="q": raise SystemExit("Cancelled.")
        if cmd=="a":
            c=ClassMeeting("COURSE 0000","Course title",[],None,None,None,False); edit_class(c); classes.append(c); continue
        m=re.fullmatch(r"d\s*(\d+)",cmd)
        if m and 1 <= int(m.group(1)) <= len(classes): classes[int(m.group(1))-1].enabled=False; continue
        if cmd.isdigit() and 1 <= int(cmd) <= len(classes): edit_class(classes[int(cmd)-1]); continue
        print("Unknown command.")

def first_meeting(start,days):
    wd={DAY_TO_WEEKDAY[d] for d in days}
    for n in range(7):
        x=start+timedelta(days=n)
        if x.weekday() in wd: return x
    raise ValueError("No valid meeting day")

def esc(v): return v.replace("\\","\\\\").replace(";","\\;").replace(",","\\,").replace("\n","\\n")
def fold(line,limit=73):
    if len(line)<=limit:return [line]
    out=[line[:limit]]; rest=line[limit:]
    while rest: out.append(" "+rest[:limit-1]); rest=rest[limit-1:]
    return out

def generate_ics(classes,start,end,tzname):
    tz=ZoneInfo(tzname); utc=ZoneInfo("UTC"); stamp=datetime.now(utc).strftime("%Y%m%dT%H%M%SZ")
    lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Class Schedule Converter V2//EN","CALSCALE:GREGORIAN","METHOD:PUBLISH",f"X-WR-TIMEZONE:{tzname}"]
    for c in classes:
        if not c.schedulable: continue
        fd=first_meeting(start,c.days); s=datetime.combine(fd,c.start_time); e=datetime.combine(fd,c.end_time)
        rule="FREQ=WEEKLY;BYDAY="+",".join(DAY_TO_ICAL[d] for d in c.days)
        if end:
            until=datetime.combine(end+timedelta(days=1),time.min,tz).astimezone(utc).strftime("%Y%m%dT%H%M%SZ"); rule += ";UNTIL="+until
        event=["BEGIN:VEVENT",f"UID:{uuid.uuid4()}@class-schedule-converter-v2",f"DTSTAMP:{stamp}",f"DTSTART;TZID={tzname}:{s:%Y%m%dT%H%M%S}",f"DTEND;TZID={tzname}:{e:%Y%m%dT%H%M%S}",f"RRULE:{rule}",f"SUMMARY:{esc(c.course_code)}",f"DESCRIPTION:{esc(c.course_title)}"]
        if c.location: event.append("LOCATION:"+esc(c.location))
        event.append("END:VEVENT")
        for x in event: lines.extend(fold(x))
    lines.append("END:VCALENDAR"); return "\r\n".join(lines)+"\r\n"

def get_date(label,optional=False,default=None):
    while True:
        v=ask(label+" (YYYY-MM-DD"+(", blank for none" if optional else "")+")", default)
        if optional and not v:return None
        try:return date.fromisoformat(v)
        except (ValueError,TypeError):print("Use YYYY-MM-DD, e.g. 2026-08-26.")

def main():
    ap=argparse.ArgumentParser(description="Extract a class schedule from text/HTML and create an .ics calendar.")
    ap.add_argument("input",nargs="?",type=Path,help="Schedule .txt/.html file. Omit to paste text interactively.")
    ap.add_argument("-o","--output",type=Path,default=Path("data/test_data/output/class_schedule.ics")); ap.add_argument("--start"); ap.add_argument("--end"); ap.add_argument("--timezone",default="America/Chicago"); ap.add_argument("--yes",action="store_true"); ap.add_argument("--open",action="store_true",dest="open_file")
    args=ap.parse_args()
    if args.input: text=load_input(args.input)
    else:
        print("Paste schedule text. Finish with Ctrl-D (macOS/Linux) or Ctrl-Z then Enter (Windows):")
        text=sys.stdin.read()
    classes=parse_text(text)
    if not classes: raise SystemExit("No courses found. Try saving/copying the schedule page as text or HTML.")
    if not args.yes: review(classes)
    start=date.fromisoformat(args.start) if args.start else get_date("Semester start")
    end=date.fromisoformat(args.end) if args.end else (None if args.yes else get_date("Semester end",True))
    if end and end<start: raise SystemExit("Semester end cannot be before semester start.")
    try: ZoneInfo(args.timezone)
    except ZoneInfoNotFoundError: raise SystemExit(f"Unknown timezone: {args.timezone}")
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(generate_ics(classes,start,end,args.timezone),encoding="utf-8",newline="")
    count=sum(c.schedulable for c in classes); print(f"\nCreated {args.output} with {count} recurring class events.")
    print("Import the same .ics file into Apple Calendar, Google Calendar, or Outlook.")
    if args.open_file:
        try:webbrowser.open(args.output.resolve().as_uri())
        except Exception:pass

if __name__=="__main__": 
    main()
