from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .scintillator_diagnostics import create_scintillator_diagnostics
from .general_diagnostics import create_general_diagnostics
from .strip_diagnostics import create_strip_diagnostics


class DiagnosticsManager:

    def __init__(self):

        self.processed_runs: set[int] = set()
        self.current_run: int | None = None
        self.state = "waiting"
        self.last_error: str | None = None

        # Keep ROOT objects alive
        self.scintillator_results: dict[str, Any] = {}
        self.general_results: dict[str, Any] = {}
        self.strip_results: dict[str, Any] = {}

        # Successful browser items
        self.scintillator_items: list[dict[str, Any]] = []
        self.general_diagnostic_items: list[dict[str, Any]] = []
        self.strip_items: list[dict[str, Any]] = []

        # Failed plots
        self.scintillator_failures: list[dict[str, Any]] = []
        self.general_failures: list[dict[str, Any]] = []
        self.strip_failures: list[dict[str, Any]] = []


    def status(self) -> dict:

        return {
            "diagnostics_state": self.state,
            "diagnostics_run": self.current_run,
            "diagnostics_error": self.last_error,

            "scintillator_available": bool(self.scintillator_results),
            "general_diagnostics_available": bool(self.general_results),
            "strip_diagnostics_available": bool(self.strip_results),

            "scintillator_items": self.scintillator_items,
            "general_diagnostic_items": self.general_diagnostic_items,
            "strip_items": self.strip_items,

            "scintillator_failures": self.scintillator_failures,
            "general_diagnostics_failures": self.general_failures,
            "strip_failures": self.strip_failures,

            "scintillator_failure_count": len(self.scintillator_failures),
            "general_failure_count": len(self.general_failures),
            "strip_failure_count": len(self.strip_failures),
        }


    def _get_run_files(self, monitor) -> list[Path]:

        files: list[Path] = []

        for subrun in sorted(monitor.files_by_subrun):
            files.extend(
                sorted(
                    monitor.files_by_subrun[subrun]
                )
            )

        return files


    def _build_items(
        self,
        results: dict[str, Any],
        web_folder: str,
    ) -> list[dict[str, Any]]:

        return [
            {
                "name": name,
                "quantity": info["quantity"],
                "group": info["group"],
                "group_title": info["group_title"],
                "url": (
                    f"/Objects/{web_folder}/"
                    f"{name}/root.json"
                ),
            }
            for name, info in results.items()
        ]


    def _register_results(
        self,
        results: dict[str, Any],
        web_folder: str,
        register_canvas: Callable[
            [str, str, Any],
            None
        ],
    ) -> None:

        for name, info in results.items():

            canvas = info.get("canvas")

            if canvas is None:
                print(
                    f"[WARNING] No canvas available for "
                    f"{web_folder}/{name}"
                )
                continue

            try:
                register_canvas(
                    web_folder,
                    name,
                    canvas,
                )

            except Exception as error:
                print(
                    f"[WARNING] Could not register "
                    f"{web_folder}/{name}: {error}"
                )


    def process_if_ready(
        self,
        monitor,
        register_canvas: Callable[
            [str, str, Any],
            None
        ],
    ) -> bool:

        if monitor.current_run is None:
            return False

        if not monitor.run_complete:
            return False

        run_number = monitor.current_run

        if run_number in self.processed_runs:
            return False

        root_files = self._get_run_files(
            monitor
        )

        if not root_files:
            return False

        self.current_run = run_number
        self.state = "processing"
        self.last_error = None

        # Clear previous run
        self.scintillator_results = {}
        self.general_results = {}
        self.strip_results = {}

        self.scintillator_items = []
        self.general_diagnostic_items = []
        self.strip_items = []

        self.scintillator_failures = []
        self.general_failures = []
        self.strip_failures = []

        print()
        print("=" * 72)
        print(
            f"Starting diagnostics for "
            f"run {run_number:05d}"
        )
        print("=" * 72)

        # -------------------------------------------------
        # Scintillator diagnostics
        # -------------------------------------------------

        try:
            output = create_scintillator_diagnostics(
                root_files=root_files,
                run_number=run_number,
                number_of_threads=8,
            )

            results = output.get("results", {})
            failures = output.get("failures", [])

            self.scintillator_results = results
            self.scintillator_failures = failures

            self._register_results(
                results=results,
                web_folder="ScintillatorDiagnostics",
                register_canvas=register_canvas,
            )

            self.scintillator_items = self._build_items(
                results=results,
                web_folder="ScintillatorDiagnostics",
            )

        except Exception as error:

            print(
                f"[WARNING] Entire scintillator "
                f"diagnostics failed: {error}"
            )

            self.scintillator_failures = [
                {
                    "quantity": "all",
                    "group": "scintillator",
                    "group_title": "Scintillator Diagnostics",
                    "error": str(error),
                }
            ]

        # -------------------------------------------------
        # General diagnostics
        # -------------------------------------------------

        try:
            output = create_general_diagnostics(
                root_files=root_files,
                run_number=run_number,
                number_of_threads=8,
            )

            results = output.get("results", {})
            failures = output.get("failures", [])

            self.general_results = results
            self.general_failures = failures

            self._register_results(
                results=results,
                web_folder="GeneralDiagnostics",
                register_canvas=register_canvas,
            )

            self.general_diagnostic_items = self._build_items(
                results=results,
                web_folder="GeneralDiagnostics",
            )

        except Exception as error:

            print(
                f"[WARNING] Entire general "
                f"diagnostics failed: {error}"
            )

            self.general_failures = [
                {
                    "quantity": "all",
                    "group": "general",
                    "group_title": "General Diagnostics",
                    "error": str(error),
                }
            ]

        # -------------------------------------------------
        # Strip diagnostics
        # -------------------------------------------------

        try:
            output = create_strip_diagnostics(
                root_files=root_files,
                run_number=run_number,
                number_of_threads=8,
            )

            results = output.get("results", {})
            failures = output.get("failures", [])

            self.strip_results = results
            self.strip_failures = failures

            self._register_results(
                results=results,
                web_folder="StripDiagnostics",
                register_canvas=register_canvas,
            )

            self.strip_items = self._build_items(
                results=results,
                web_folder="StripDiagnostics",
            )

        except Exception as error:

            print(
                f"[WARNING] Entire strip "
                f"diagnostics failed: {error}"
            )

            self.strip_failures = [
                {
                    "quantity": "all",
                    "group": "strip",
                    "group_title": "Strip Diagnostics",
                    "error": str(error),
                }
            ]

        # -------------------------------------------------
        # Mark run complete
        # -------------------------------------------------

        self.processed_runs.add(
            run_number
        )

        self.state = "ready"

        print()
        print("=" * 72)
        print(
            f"Diagnostics completed for "
            f"run {run_number:05d}"
        )
        print(
            f"Scintillator plots : "
            f"{len(self.scintillator_items)}"
        )
        print(
            f"Scintillator failed: "
            f"{len(self.scintillator_failures)}"
        )
        print(
            f"General plots      : "
            f"{len(self.general_diagnostic_items)}"
        )
        print(
            f"General failed     : "
            f"{len(self.general_failures)}"
        )
        print(
            f"Strip plots        : "
            f"{len(self.strip_items)}"
        )
        print(
            f"Strip failed       : "
            f"{len(self.strip_failures)}"
        )
        print("=" * 72)

        return True