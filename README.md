# Calendar Manager

Convert a class schedule into a portable `.ics` calendar that can be imported into Apple Calendar, Google Calendar, or Microsoft Outlook.

The current V3 script supports three input modes:

- Plain-text schedule exports
- Saved/rendered HTML schedule pages
- Authenticated schedule-page URLs via Playwright

It parses course codes/titles, meeting days, times, and locations; lets you review or edit the detected classes; and generates weekly recurring calendar events for the semester.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Chromium installed through Playwright for URL mode

## Setup

From the project root:

```bash
uv sync
uv run playwright install chromium
```

If you already have a `.venv`, `uv sync` will manage the project environment from `pyproject.toml`.

## Usage

Assuming the script is located at `src/class_schedule_to_ics_v3.py`:

### Parse a text file

```bash
uv run python src/class_schedule_to_ics_v3.py data/test_data/input/test.txt
```

### Parse a rendered HTML file

```bash
uv run python src/class_schedule_to_ics_v3.py data/test_data/input/test.html
```

### Parse a schedule directly from a URL

```bash
uv run python src/class_schedule_to_ics_v3.py "https://student-search.app.vanderbilt.edu/..."
```

For authenticated pages, V3 launches Chromium and waits for the rendered schedule. On the first run, sign in normally and complete MFA if required. The Playwright browser profile can preserve the authenticated session for later runs.

### Headless URL mode

After you have authenticated successfully at least once:

```bash
uv run python src/class_schedule_to_ics_v3.py \
  "https://student-search.app.vanderbilt.edu/..." \
  --headless
```

If the login session has expired, rerun without `--headless` so you can authenticate interactively.

### Fully specified run

```bash
uv run python src/class_schedule_to_ics_v3.py \
  "https://student-search.app.vanderbilt.edu/..." \
  --start 2026-08-26 \
  --end 2026-12-11 \
  --timezone America/Chicago \
  --yes \
  --headless \
  --open
```

## Output

By default, configure the script to use:

```python
default=Path.home() / "Desktop" / "class_schedule.ics"
```

This saves the generated calendar to the current user's Desktop.

You can override the destination with `-o` or `--output`:

```bash
uv run python src/class_schedule_to_ics_v3.py schedule.html \
  -o ~/Desktop/fall_2026_classes.ics
```

If accepting `~` in user-supplied output paths, the argument definition should use:

```python
type=lambda p: Path(p).expanduser()
```

## Calendar behavior

The generated `.ics` file:

- Creates one recurring event per schedulable class
- Uses weekly recurrence rules based on `M`, `T`, `W`, `R`, and `F`
- Interprets `R` as Thursday
- Starts each course on its first valid meeting day on or after the semester start date
- Optionally stops recurrence at the semester end date
- Can use an indefinite recurrence if no end date is supplied
- Includes course code, course title, meeting time, and location
- Skips TBA meetings unless they are manually edited into schedulable events

For example, if the semester starts on Wednesday and a course meets `MW`, its first event is Wednesday and its next occurrence is the following Monday.

## Authentication and privacy

URL mode uses Playwright to load the schedule in a real Chromium browser. The script does not need your university password or MFA secret. Authentication remains in the browser session.

The persistent browser profile should be treated as sensitive because it can contain authenticated cookies. Do not commit it to Git or share it.

Recommended `.gitignore` entries include:

```gitignore
.venv/
__pycache__/
*.pyc
*.ics
.class-schedule-converter/
.DS_Store
```

If the Playwright profile is stored under your home directory (for example `~/.class-schedule-converter/chromium-profile`), it is already outside the repository.

## Project structure

A simple layout is:

```text
calendar_mngr/
├── pyproject.toml
├── README.md
├── src/
│   └── class_schedule_to_ics_v3.py
└── data/
    └── test_data/
        ├── input/
        └── output/
```

## Current limitations

- The Vanderbilt HTML parser depends on the current schedule DOM structure/classes. If Vanderbilt redesigns the page, its selectors may need updating.
- URL mode requires Playwright and its Chromium installation.
- Authentication may periodically expire and require an interactive login/MFA session.
- TBA courses cannot be placed on a calendar until meeting days/times are known.

## Development direction

The current architecture deliberately separates schedule extraction from calendar generation. Future versions can add browser extensions, other university schedule formats, direct calendar APIs, or additional parsers without replacing the `.ics` generation logic.
