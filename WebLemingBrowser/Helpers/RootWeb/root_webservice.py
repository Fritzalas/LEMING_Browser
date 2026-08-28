from __future__ import annotations

import json
import os
import sys
import time

import ROOT


# =========================================================
# PATH SETUP
# =========================================================

current = os.path.dirname(
    os.path.realpath(__file__)
)

parent = os.path.dirname(
    current
)

if parent not in sys.path:
    sys.path.append(
        parent
    )


# =========================================================
# IMPORTS
# =========================================================

from Helpers.FileFinder.run_monitor import (
    LiveRunMonitor,
    now_text,
)


# =========================================================
# ROOT WEB SERVICE
# =========================================================

class RootWebService:

    def __init__(
        self,
        monitor,
        diagnostics_manager,
        dashboard_html,
        port: int = 8080,
    ) -> None:

        self.monitor = (
            monitor
        )

        self.diagnostics_manager = (
            diagnostics_manager
        )

        self.port = (
            port
        )


        # -------------------------------------------------
        # Keep all registered ROOT objects alive.
        #
        # Keys look like:
        #
        #   ScintillatorDiagnostics/<name>
        #   GeneralDiagnostics/<name>
        #
        # -------------------------------------------------

        self.registered_objects = {}


        # -------------------------------------------------
        # Status object
        # -------------------------------------------------

        self.status_object = (
            ROOT.TNamed(
                "status",
                "{}",
            )
        )


        # -------------------------------------------------
        # ROOT HTTP server
        # -------------------------------------------------

        self.server = (
            ROOT.THttpServer(
                f"http:{port}"
            )
        )


        # -------------------------------------------------
        # Main monitor/status object
        # -------------------------------------------------

        self.server.Register(
            "monitor",
            self.status_object,
        )


        # -------------------------------------------------
        # Custom HTML dashboard
        # -------------------------------------------------

        self.server.SetDefaultPage(
            str(
                dashboard_html
            )
        )


        self.publish_status()


    # =====================================================
    # STATUS
    # =====================================================

    def publish_status(
        self,
    ) -> None:

        payload = (
            self.monitor.status()
        )

        payload.update(
            self.diagnostics_manager
            .status()
        )

        self.status_object.SetTitle(
            json.dumps(
                payload
            )
        )


    # =====================================================
    # ROOT HTTP EVENTS
    # =====================================================

    def process_http_events(
        self,
    ) -> None:

        self.server.ProcessRequests()

        ROOT.gSystem.ProcessEvents()


    # =====================================================
    # REGISTER DIAGNOSTIC CANVAS
    # =====================================================

    def register_diagnostic_canvas(
        self,
        folder: str,
        name: str,
        canvas,
    ) -> None:

        if canvas is None:

            raise ValueError(
                f"Cannot register canvas "
                f"'{name}': canvas is None."
            )


        # -------------------------------------------------
        # ROOT object name
        # -------------------------------------------------

        canvas.SetName(
            name
        )


        # -------------------------------------------------
        # Ensure all pads/primitives are finalized before
        # exposing the object through THttpServer.
        # -------------------------------------------------

        canvas.Modified()
        canvas.Update()


        # -------------------------------------------------
        # Keep PyROOT object alive.
        #
        # Folder is included in key so general/scintillator
        # diagnostics can never overwrite each other.
        # -------------------------------------------------

        key = (
            f"{folder}/{name}"
        )

        self.registered_objects[
            key
        ] = canvas


        # -------------------------------------------------
        # Register on ROOT server.
        #
        # Examples:
        #
        # /Objects/ScintillatorDiagnostics/<name>/root.json
        #
        # /Objects/GeneralDiagnostics/<name>/root.json
        #
        # -------------------------------------------------

        self.server.Register(
            folder,
            canvas,
        )


        print(
            f"Registered diagnostic canvas: "
            f"{folder}/{name}"
        )


    # =====================================================
    # STOP SERVER
    # =====================================================

    def stop(
        self,
    ) -> None:

        self.server = None


# =========================================================
# MAIN SERVICE LOOP
# =========================================================

def run_root_loop(
    monitor,
    diagnostics,
    webservice: RootWebService,
) -> None:

    next_scan = 0.0


    while True:

        now = (
            time.monotonic()
        )


        # =================================================
        # FILESYSTEM MONITORING
        # =================================================

        if now >= next_scan:

            events = (
                monitor.update()
            )


            for event in events:

                print(
                    f"[{now_text()}] "
                    f"{event}"
                )


            # -------------------------------------------------
            # Diagnostics manager handles:
            #
            #   - whether run is complete
            #   - whether run was already processed
            #   - scintillator diagnostics
            #   - general diagnostics
            #   - registering each canvas into the correct
            #     THttpServer folder
            #
            # -------------------------------------------------

            diagnostics.process_if_ready(
                monitor=monitor,

                register_canvas=(
                    webservice
                    .register_diagnostic_canvas
                ),
            )


            # -------------------------------------------------
            # Publish latest monitor + diagnostics state.
            # -------------------------------------------------

            webservice.publish_status()


            # -------------------------------------------------
            # Active run:
            #     usually 2 seconds
            #
            # Complete run:
            #     usually 30 seconds while waiting for next run
            #
            # -------------------------------------------------

            next_scan = (
                now
                + monitor.next_poll_seconds()
            )


        # =================================================
        # KEEP ROOT HTTP SERVER RESPONSIVE
        # =================================================

        webservice.process_http_events()


        # Avoid busy-spinning.
        time.sleep(
            0.05
        )


# =========================================================
# STARTUP INFORMATION
# =========================================================

def print_startup(
    monitor: LiveRunMonitor,
    port: int,
) -> None:

    print(
        "=" * 72
    )

    print(
        "ROOT Live Run Dashboard"
    )

    print(
        "=" * 72
    )


    print(
        f"Watch directory : "
        f"{monitor.directory}"
    )


    print(
        f"Browser         : "
        f"http://localhost:{port}"
    )


    print(
        f"Active polling  : "
        f"{monitor.config.active_poll_seconds:.1f} s"
    )


    print(
        f"Complete after  : "
        f"{monitor.config.complete_after_seconds:.1f} s"
    )


    print(
        f"Idle polling    : "
        f"{monitor.config.idle_poll_seconds:.1f} s"
    )


    print(
        "=" * 72
    )