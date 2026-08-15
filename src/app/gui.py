from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QDate, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDateEdit, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

# Reuse the tested engine in src/main.py without changing it.
# These names match the V3 script produced during development.
try:
    from main import (
        ClassMeeting,
        generate_ics,
        load_input,
        parse_text,
    )
except ImportError as exc:
    raise RuntimeError(
        "src/main.py must expose ClassMeeting, generate_ics, load_input, and parse_text."
    ) from exc

from .web_loader import load_vanderbilt_schedule


class ScheduleWorker(QThread):
    loaded = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            self.loaded.emit(load_vanderbilt_schedule(self.url))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Class Schedule Converter")
        self.resize(760, 620)
        self.classes: list[ClassMeeting] = []
        self.checkboxes: list[QCheckBox] = []
        self.worker = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        layout.addWidget(QLabel("Vanderbilt schedule URL"))
        url_row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://student-search.app.vanderbilt.edu/...")
        self.load_url_btn = QPushButton("Load Schedule")
        self.load_url_btn.clicked.connect(self.load_url)
        url_row.addWidget(self.url)
        url_row.addWidget(self.load_url_btn)
        layout.addLayout(url_row)

        self.file_btn = QPushButton("Or open a saved TXT / HTML file")
        self.file_btn.clicked.connect(self.load_file)
        layout.addWidget(self.file_btn)

        layout.addWidget(QLabel("Classes found"))
        self.class_box = QWidget()
        self.class_layout = QVBoxLayout(self.class_box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.class_box)
        layout.addWidget(scroll, 1)

        form = QFormLayout()
        self.start_date = QDateEdit(QDate.currentDate())
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("MMM d, yyyy")
        self.end_date = QDateEdit(QDate.currentDate().addMonths(4))
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("MMM d, yyyy")
        form.addRow("Semester starts", self.start_date)
        form.addRow("Semester ends", self.end_date)
        layout.addLayout(form)

        self.create_btn = QPushButton("Create & Open Calendar")
        self.create_btn.clicked.connect(self.create_calendar)
        layout.addWidget(self.create_btn)

        self.status = QLabel("")
        layout.addWidget(self.status)

    def set_busy(self, busy: bool, message: str = ""):
        self.load_url_btn.setEnabled(not busy)
        self.file_btn.setEnabled(not busy)
        self.create_btn.setEnabled(not busy)
        self.status.setText(message)

    def load_url(self):
        url = self.url.text().strip()
        if not url.startswith(("http://", "https://")):
            QMessageBox.warning(self, "Invalid URL", "Paste the full schedule URL.")
            return
        self.set_busy(True, "Opening Chrome and loading the schedule…")
        self.worker = ScheduleWorker(url)
        self.worker.loaded.connect(self.on_html_loaded)
        self.worker.failed.connect(self.on_load_failed)
        self.worker.start()

    def on_html_loaded(self, html: str):
        try:
            # main.py's HTML-aware loader normally accepts a Path. Here the
            # web loader returns the schedule container itself, so parse the
            # visible text using the existing HTML conversion if available.
            try:
                from main import html_to_text
                text = html_to_text(html)
            except ImportError:
                text = html
            classes = parse_text(text)
            if not classes:
                # Some V3 variants expose a Vanderbilt-specific parser.
                try:
                    from main import parse_vanderbilt_html
                    classes = parse_vanderbilt_html(html)
                except ImportError:
                    pass
            if not classes:
                raise ValueError("The schedule loaded, but no classes could be parsed.")
            self.populate_classes(classes)
            self.set_busy(False, f"Loaded {len(classes)} classes.")
        except Exception as exc:
            self.on_load_failed(str(exc))

    def on_load_failed(self, message: str):
        self.set_busy(False, "")
        QMessageBox.critical(self, "Could not load schedule", message)

    def load_file(self):
        name, _ = QFileDialog.getOpenFileName(
            self, "Open schedule", "", "Schedule files (*.txt *.html *.htm);;All files (*)"
        )
        if not name:
            return
        try:
            classes = parse_text(load_input(Path(name)))
            if not classes:
                raise ValueError("No classes were found in this file.")
            self.populate_classes(classes)
            self.status.setText(f"Loaded {len(classes)} classes.")
        except Exception as exc:
            QMessageBox.critical(self, "Could not read file", str(exc))

    def populate_classes(self, classes):
        self.classes = classes
        while self.class_layout.count():
            item = self.class_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.checkboxes = []
        for c in classes:
            days = "".join(c.days) if c.days else "TBA"
            start = c.start_time.strftime("%-I:%M %p") if c.start_time else "TBA"
            end = c.end_time.strftime("%-I:%M %p") if c.end_time else "TBA"
            label = f"{c.course_code} — {days} — {start}–{end} — {c.location or 'TBA'}"
            cb = QCheckBox(label)
            cb.setChecked(bool(c.schedulable))
            cb.setEnabled(bool(c.days and c.start_time and c.end_time))
            self.class_layout.addWidget(cb)
            self.checkboxes.append(cb)
        self.class_layout.addStretch()

    def create_calendar(self):
        if not self.classes:
            QMessageBox.information(self, "No schedule", "Load a schedule first.")
            return

        selected = []
        for c, cb in zip(self.classes, self.checkboxes):
            c.enabled = cb.isChecked()
            selected.append(c)

        qstart = self.start_date.date()
        qend = self.end_date.date()
        start = qstart.toPython()
        end = qend.toPython()
        if end < start:
            QMessageBox.warning(self, "Invalid dates", "The end date must be after the start date.")
            return

        default = str(Path.home() / "Desktop" / "class_schedule.ics")
        name, _ = QFileDialog.getSaveFileName(
            self, "Save calendar", default, "Calendar files (*.ics)"
        )
        if not name:
            return
        output = Path(name)
        if output.suffix.lower() != ".ics":
            output = output.with_suffix(".ics")

        try:
            output.write_text(
                generate_ics(selected, start, end, "America/Chicago"),
                encoding="utf-8",
                newline="",
            )
            import subprocess
            subprocess.run(["open", str(output)], check=False)
            self.status.setText(f"Created {output}")
        except Exception as exc:
            QMessageBox.critical(self, "Could not create calendar", str(exc))


def run():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
