from pathlib import Path

import ROOT

from Helpers.Config.config import (
    WATCH_DIRECTORY,
    PORT,
    ACTIVE_POLL_SECONDS,
    COMPLETE_AFTER_SECONDS,
    IDLE_POLL_SECONDS,
)
from Helpers.FileFinder.run_monitor import (
    LiveRunMonitor,
    MonitorConfig,
)
from Helpers.RootWeb.root_webservice import (
    RootWebService,
    print_startup,
    run_root_loop,
)
from Helpers.Diagnostics.diagnostics_manager import (
    DiagnosticsManager,
)


def main() -> None:
    ROOT.gROOT.SetBatch(True)

    base_directory = (
        Path(__file__)
        .resolve()
        .parent
    )

    dashboard_html = (
        base_directory
        / "dashboard.html"
    )

    # ---------------------------------------------------------
    # Run monitor
    # ---------------------------------------------------------

    monitor_config = MonitorConfig(
        watch_directory=WATCH_DIRECTORY,
        active_poll_seconds=ACTIVE_POLL_SECONDS,
        complete_after_seconds=COMPLETE_AFTER_SECONDS,
        idle_poll_seconds=IDLE_POLL_SECONDS,
    )

    monitor = LiveRunMonitor(
        monitor_config
    )

    diagnostics = DiagnosticsManager()

    # ---------------------------------------------------------
    # ROOT web service
    # ---------------------------------------------------------

    webservice = RootWebService(
        monitor=monitor,
        diagnostics_manager=diagnostics,
        dashboard_html=dashboard_html,
        port=PORT,
    )

    # ---------------------------------------------------------
    # Startup
    # ---------------------------------------------------------

    print_startup(
        monitor,
        PORT,
    )

    # One scan immediately at startup.
    for event in monitor.update():
        print(
            f"[startup] {event}"
        )

    webservice.publish_status()

    # ---------------------------------------------------------
    # Permanent service loop
    # ---------------------------------------------------------

    try:
        run_root_loop(
            monitor,
            diagnostics,
            webservice,
        )

    except KeyboardInterrupt:
        print(
            "\nStopping ROOT dashboard..."
        )

    finally:
        
        webservice.stop()

        print(
            "ROOT dashboard stopped."
        )


if __name__ == "__main__":
    main()