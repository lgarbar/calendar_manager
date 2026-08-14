#!/usr/bin/env python3
"""Class schedule text -> importable iCalendar (.ics) file.

Designed for schedule text shaped like the supplied test.txt. It parses course
blocks, previews them, prompts for semester dates, and writes weekly recurring
events compatible with Apple Calendar, Google Calendar, and Outlook.
"""

from __future__ import annotations

import argparse
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

COURSE_RE = re.compile(r"^([A-Z][A-Z0-9-]*\s+\d+[A-Z]?)\s*:\s*(.+?)\s*$")
TIME_RE = re.compile(
    r"^(\d{1,2}:\d{2}\s*[ap](?:m)?)\s*-\s*(\d{1,2}:\d{2}\s*[ap](?:m)?)$",
    re.IGNORECASE,
)
DAY_RE = re.compile(r"^[MTWRF]+$")
DAY_TO_ICAL = {"M": "MO", "T": "TU", "W": "WE", "R": "TH", "F": "FR"}
DAY_TO_WEEKDAY = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4}


@dataclass
class ClassMeeting:
    course_code: str
    course_title: str
    days: list[str]
    start_time: Optional[time]
    end_time: Optional[time]
    location: Optional[str]

    @property
    def schedulable(self) -> bool:
        return bool(self.days and self.start_time and self.end_time)


def parse_clock(value: str) -> time:
    cleaned = re.sub(r"\s+", "", value.lower()).replace("a", "am").replace("p", "pm")
    cleaned = cleaned.replace("amm", "am").replace("pmm", "pm")
    return datetime.strptime(cleaned, "%I:%M%p").time()


def clean_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def split_course_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if COURSE_RE.match(line):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def parse_block(block: list[str]) -> ClassMeeting:
    match = COURSE_RE.match(block[0])
    if not match:
        raise ValueError(f"Invalid course header: {block[0]}")
    code, title = match.groups()

    days: list[str] = []
    start: Optional[time] = None
    end: Optional[time] = None
    location: Optional[str] = None

    time_index: Optional[int] = None
    for i, line in enumerate(block[1:], start=1):
        if line.upper() == "TBA":
            continue

        # The enrollment/detail row may end with the day code, e.g. "... Enrolled MW".
        tokens = line.split()
        if tokens and DAY_RE.fullmatch(tokens[-1]):
            days = list(tokens[-1])

        tm = TIME_RE.match(line)
        if tm:
            start = parse_clock(tm.group(1))
            end = parse_clock(tm.group(2))
            time_index = i
            break

    if time_index is not None and time_index + 1 < len(block):
        candidate = block[time_index + 1]
        if candidate.upper() != "TBA" and not candidate.startswith("Note:"):
            location = candidate

    return ClassMeeting(code, title, days, start, end, location)


def parse_schedule(path: Path) -> list[ClassMeeting]:
    text = path.read_text(encoding="utf-8-sig")
    return [parse_block(block) for block in split_course_blocks(clean_lines(text))]


def first_meeting_on_or_after(start: date, days: list[str]) -> date:
    weekdays = {DAY_TO_WEEKDAY[d] for d in days}
    for offset in range(7):
        candidate = start + timedelta(days=offset)
        if candidate.weekday() in weekdays:
            return candidate
    raise ValueError("No valid meeting days")


def escape_ics(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold_ics(line: str, limit: int = 73) -> list[str]:
    # Conservative ASCII-oriented folding. Continuation lines begin with one space.
    if len(line) <= limit:
        return [line]
    out = [line[:limit]]
    rest = line[limit:]
    while rest:
        out.append(" " + rest[: limit - 1])
        rest = rest[limit - 1 :]
    return out


def format_local(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def generate_ics(
    classes: list[ClassMeeting],
    semester_start: date,
    semester_end: Optional[date],
    timezone: str,
) -> str:
    tz = ZoneInfo(timezone)  # validates the requested timezone
    _ = tz
    now_utc = datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Class Schedule Converter//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-TIMEZONE:{timezone}",
    ]

    for course in classes:
        if not course.schedulable:
            continue
        first_date = first_meeting_on_or_after(semester_start, course.days)
        start_dt = datetime.combine(first_date, course.start_time)
        end_dt = datetime.combine(first_date, course.end_time)
        byday = ",".join(DAY_TO_ICAL[d] for d in course.days)
        rrule = f"FREQ=WEEKLY;BYDAY={byday}"
        if semester_end:
            # Inclusive through the requested local end date.
            until = datetime.combine(semester_end + timedelta(days=1), time.min, ZoneInfo(timezone))
            until_utc = until.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
            rrule += f";UNTIL={until_utc}"

        event = [
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid4()}@class-schedule-converter",
            f"DTSTAMP:{now_utc}",
            f"DTSTART;TZID={timezone}:{format_local(start_dt)}",
            f"DTEND;TZID={timezone}:{format_local(end_dt)}",
            f"RRULE:{rrule}",
            f"SUMMARY:{escape_ics(course.course_code)}",
            f"DESCRIPTION:{escape_ics(course.course_title)}",
        ]
        if course.location:
            event.append(f"LOCATION:{escape_ics(course.location)}")
        event.append("END:VEVENT")
        for line in event:
            lines.extend(fold_ics(line))

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def prompt_date(label: str, optional: bool = False) -> Optional[date]:
    while True:
        suffix = " (YYYY-MM-DD, blank for none)" if optional else " (YYYY-MM-DD)"
        raw = input(label + suffix + ": ").strip()
        if optional and not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            print("Please use YYYY-MM-DD, for example 2026-08-26.")


def preview(classes: list[ClassMeeting]) -> None:
    print("\nParsed classes:\n")
    for i, c in enumerate(classes, 1):
        if c.schedulable:
            days = "".join(c.days)
            start = c.start_time.strftime("%I:%M %p").lstrip("0")
            end = c.end_time.strftime("%I:%M %p").lstrip("0")
            print(f"{i}. {c.course_code} - {c.course_title}")
            print(f"   {days} | {start} - {end} | {c.location or 'No location'}")
        else:
            print(f"{i}. {c.course_code} - {c.course_title} [SKIPPED: TBA/unscheduled]")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert class schedule text to an importable .ics calendar.")
    parser.add_argument("input", type=Path, help="Path to schedule text file")
    parser.add_argument("-o", "--output", type=Path, default=Path("class_schedule.ics"))
    parser.add_argument("--start", help="Semester start date, YYYY-MM-DD")
    parser.add_argument("--end", help="Semester end date, YYYY-MM-DD; omit for no end date")
    parser.add_argument("--timezone", default="America/Chicago", help="IANA timezone (default: America/Chicago)")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    classes = parse_schedule(args.input)
    if not classes:
        raise SystemExit("No course blocks were found in the input file.")
    preview(classes)

    semester_start = date.fromisoformat(args.start) if args.start else prompt_date("Semester start")
    semester_end = date.fromisoformat(args.end) if args.end else prompt_date("Semester end", optional=True)
    if semester_end and semester_end < semester_start:
        raise SystemExit("Semester end cannot be before semester start.")

    if not args.yes:
        answer = input("Generate the calendar with these classes? [Y/n]: ").strip().lower()
        if answer not in ("", "y", "yes"):
            raise SystemExit("Cancelled.")

    ics = generate_ics(classes, semester_start, semester_end, args.timezone)
    args.output.write_text(ics, encoding="utf-8", newline="")
    count = sum(c.schedulable for c in classes)
    print(f"Created {args.output} with {count} recurring class events.")


if __name__ == "__main__":
    main()
