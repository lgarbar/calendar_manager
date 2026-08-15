# Calendar Manager

Calendar Manager converts a class schedule into a portable `.ics`
calendar that can be imported into Apple Calendar, Google Calendar, or
Microsoft Outlook.

The project supports schedule text files, saved/rendered HTML, and an
authenticated Vanderbilt schedule URL. The desktop app provides a
graphical interface with class selection and calendar date pickers, so
normal use does not require the Terminal.

## Requirements

For development/building:

-   macOS
-   Python 3.11+
-   [uv](https://docs.astral.sh/uv/)
-   Google Chrome
-   Git

Google Chrome is used by Playwright for authenticated schedule loading.
This keeps the packaged application much smaller than bundling a
separate Chromium browser.

## Clone and install

``` bash
git clone https://github.com/lgarbar/calendar_manager.git
cd calendar_mngr
uv sync
```

If the repository's `pyproject.toml` does not yet contain the GUI/build
dependencies, add them once:

``` bash
uv add playwright pyside6
uv add --dev pyinstaller
```

Because the desktop app launches the locally installed Google Chrome
(`channel="chrome"`), a separate `playwright install chromium` step is
not required.

## Run the desktop app from the repository

After cloning and installing dependencies:

``` bash
uv run python -m app.gui
```

The app opens as a normal graphical window. Paste the Vanderbilt
schedule URL, click **Load Schedule**, choose the semester start/end
dates with the calendar controls, select the classes to include, and
click **Create & Open Calendar**.

The first time a Vanderbilt URL is loaded, Chrome may ask you to sign in
and complete MFA. Calendar Manager uses a dedicated persistent Chrome
profile so the authenticated session can be reused until Vanderbilt
expires it. The application does not ask for or store your Vanderbilt
password.

## Existing command-line program

The existing CLI remains in `src/main.py` and does not need to be
modified for the GUI.

Examples:

``` bash
uv run python src/main.py schedule.txt
uv run python src/main.py schedule.html
```

If your current `main.py` already supports URL mode, that workflow can
remain available as well.

## Project layout

``` text
calendar_mngr/
├── README.md
├── pyproject.toml
├── src/
│   ├── main.py
│   └── app/
│       ├── __init__.py
│       ├── gui.py
│       └── web_loader.py
└── tests/
```

`src/main.py` remains the tested schedule/calendar engine. App-specific
code lives under `src/app/`.

## Package the macOS app yourself

The compiled `.app` should generally **not** be committed to GitHub.
Commit the source code, `pyproject.toml`, lockfile, README, and build
configuration instead. Users/developers can build the application
locally.

Install/sync dependencies:

``` bash
uv sync
```

Then build:

``` bash
uv run pyinstaller \
  --noconfirm \
  --windowed \
  --name "Calendar Manager" \
  --paths src \
  --collect-all PySide6 \
  --collect-all playwright \
  src/app/gui.py
```

PyInstaller writes the application to:

``` text
dist/Calendar Manager.app
```

Open it with:

``` bash
open "dist/Calendar Manager.app"
```

Or drag `Calendar Manager.app` into `/Applications`.

### Rebuilding

Remove old build products when necessary:

``` bash
rm -rf build dist
```

Then run the PyInstaller command again.

## GitHub

Do not commit generated application/build directories. Add at least the
following to `.gitignore`:

``` gitignore
.venv/
build/
dist/
*.spec
__pycache__/
.DS_Store
```

`uv.lock` should normally be committed so other users reproduce the
dependency versions used by the project.

## Authentication and privacy

Calendar Manager does not implement Vanderbilt authentication itself.
Playwright opens Google Chrome, Vanderbilt handles login/MFA normally,
and the app reads the rendered schedule after it appears.

The persistent browser profile is stored locally under:

``` text
~/Library/Application Support/CalendarManager/chrome-profile
```

Do not commit that directory or copy it into the repository.

## Calendar behavior

Scheduled classes become weekly recurring events. `M`, `T`, `W`, `R`,
and `F` represent Monday through Friday, with `R` representing Thursday.
TBA meetings are displayed but excluded from calendar generation by
default.

The generated `.ics` file is compatible with Apple Calendar, Google
Calendar, and Microsoft Outlook.
