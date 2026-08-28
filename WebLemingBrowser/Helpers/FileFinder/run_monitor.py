from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .file_finder import scan_runs, get_latest_run_number


@dataclass
class MonitorConfig:
    watch_directory: Path
    active_poll_seconds: float = 2.0
    complete_after_seconds: float = 30.0
    idle_poll_seconds: float = 30.0


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class LiveRunMonitor:
    """
    Keeps track of:
      - latest run
      - all subruns
      - last new subrun time
      - active/complete state
      - adaptive polling
    """

    def __init__(self, config: MonitorConfig):
        self.config = config
        self.directory = config.watch_directory.expanduser().resolve()

        if not self.directory.is_dir():
            raise RuntimeError(
                f"Watch directory does not exist: {self.directory}"
            )

        self.current_run: int | None = None
        self.known_subruns: set[int] = set()
        self.files_by_subrun: dict[int, list[Path]] = {}

        self.run_complete = False

        self.last_new_subrun_monotonic: float | None = None
        self.last_new_subrun_wallclock: str | None = None
        self.last_scan_wallclock: str | None = None

        self.last_event = "Starting monitor"

    def next_poll_seconds(self) -> float:
        if self.run_complete:
            return self.config.idle_poll_seconds

        return self.config.active_poll_seconds

    def status(self) -> dict[str, Any]:
        ordered = sorted(self.known_subruns)

        if (
            self.last_new_subrun_monotonic is not None
            and not self.run_complete
        ):
            inactive_seconds = max(
                0.0,
                time.monotonic()
                - self.last_new_subrun_monotonic
            )
        else:
            inactive_seconds = None

        if self.current_run is None:
            state = "waiting"
        elif self.run_complete:
            state = "complete"
        else:
            state = "active"

        return {
            "directory": str(self.directory),

            "current_run": self.current_run,
            "current_run_text": (
                f"{self.current_run:05d}"
                if self.current_run is not None
                else None
            ),

            "state": state,
            "run_complete": self.run_complete,

            "subrun_count": len(ordered),
            "first_subrun": ordered[0] if ordered else None,
            "latest_subrun": ordered[-1] if ordered else None,
            "subruns": ordered,

            "subrun_files": {
                f"{subrun:05d}": [
                    path.name
                    for path in self.files_by_subrun.get(
                        subrun,
                        []
                    )
                ]
                for subrun in ordered
            },

            "last_new_subrun": self.last_new_subrun_wallclock,
            "last_scan": self.last_scan_wallclock,

            "inactive_seconds": inactive_seconds,

            "complete_after_seconds":
                self.config.complete_after_seconds,

            "active_poll_seconds":
                self.config.active_poll_seconds,

            "idle_poll_seconds":
                self.config.idle_poll_seconds,

            "next_poll_seconds":
                self.next_poll_seconds(),

            "last_event":
                self.last_event,
        }

    def update(self) -> list[str]:
        """
        Perform one filesystem scan and update internal state.

        Returns a list of human-readable event messages.
        """
        events: list[str] = []

        now_mono = time.monotonic()
        self.last_scan_wallclock = now_text()

        runs = scan_runs(self.directory)

        latest_run = get_latest_run_number(runs)

        if latest_run is None:
            self.last_event = "No ROOT runs found"
            return events

        # ---------------------------------------------------------
        # First run discovered
        # ---------------------------------------------------------

        if self.current_run is None:
            self.current_run = latest_run

            self.files_by_subrun = runs[latest_run]
            self.known_subruns = set(
                self.files_by_subrun
            )

            self.last_new_subrun_monotonic = now_mono
            self.last_new_subrun_wallclock = now_text()

            self.run_complete = False

            message = (
                f"Latest run {latest_run:05d} found "
                f"with {len(self.known_subruns)} subrun(s)"
            )

            self.last_event = message
            events.append(message)

            return events

        # ---------------------------------------------------------
        # A newer run appeared
        # ---------------------------------------------------------

        if latest_run != self.current_run:
            previous_run = self.current_run

            self.current_run = latest_run

            self.files_by_subrun = runs[latest_run]
            self.known_subruns = set(
                self.files_by_subrun
            )

            self.last_new_subrun_monotonic = now_mono
            self.last_new_subrun_wallclock = now_text()

            self.run_complete = False

            message = (
                f"New run detected: "
                f"{previous_run:05d} -> {latest_run:05d}"
            )

            self.last_event = message
            events.append(message)

            return events

        # ---------------------------------------------------------
        # Current run
        # ---------------------------------------------------------

        current_subruns = runs.get(
            self.current_run,
            {}
        )

        self.files_by_subrun = current_subruns

        current_numbers = set(
            current_subruns
        )

        new_subruns = (
            current_numbers
            - self.known_subruns
        )

        # ---------------------------------------------------------
        # New subruns
        # ---------------------------------------------------------

        if new_subruns:
            if self.run_complete:
                events.append(
                    f"Run {self.current_run:05d} reopened "
                    f"after late data"
                )

            self.run_complete = False

            self.last_new_subrun_monotonic = now_mono
            self.last_new_subrun_wallclock = now_text()

            for subrun in sorted(new_subruns):
                message = (
                    f"New subrun "
                    f"{self.current_run:05d}_{subrun:05d}"
                )

                events.append(message)

            self.known_subruns.update(
                new_subruns
            )

            self.last_event = events[-1]

        # ---------------------------------------------------------
        # Completion timeout
        # ---------------------------------------------------------

        if (
            not self.run_complete
            and
            self.last_new_subrun_monotonic
            is not None
        ):
            inactive_for = (
                now_mono
                - self.last_new_subrun_monotonic
            )

            if (
                inactive_for
                >= self.config.complete_after_seconds
            ):
                self.run_complete = True

                message = (
                    f"Run {self.current_run:05d} complete: "
                    f"{len(self.known_subruns)} subrun(s)"
                )

                events.append(message)
                self.last_event = message

        return events