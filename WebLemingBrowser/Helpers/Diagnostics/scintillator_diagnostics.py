from __future__ import annotations

from pathlib import Path
from typing import Any

import re

from Helpers.RDataFrame.rdataframehelper import (
    get_general_rdataframe,
)

from Helpers.Histograms.tramhisto import (
    get_tram_histograms,
)

from Helpers.Plot.plottram import (
    plot_tram_histograms,
)


# =========================================================
# QUANTITIES
# =========================================================

SCINTILLATOR_ENERGY_QUANTITIES = [
    "MuonEntranceEnergy",
    "TriggerLEnergy",
    "TriggerREnergy",
    "AtomicEnergy",
]


TRACKER_SCINTILLATOR_ENERGY_QUANTITIES = [
    "LN1Energy",
    "LN2Energy",
    "LN3Energy",

    "LF1Energy",
    "LF2Energy",
    "LF3Energy",

    "RN1Energy",
    "RN2Energy",
    "RN3Energy",

    "RF1Energy",
    "RF2Energy",
    "RF3Energy",
]


SCINTILLATOR_TIME_QUANTITIES = [
    "MuonEntranceTime",
    "TriggerLTime",
    "TriggerRTime",
    "AtomicTime",
    "AtomicDriftTime",
]


TRACKER_SCINTILLATOR_TIME_QUANTITIES = [
    "LN1Time",
    "LN2Time",
    "LN3Time",

    "LF1Time",
    "LF2Time",
    "LF3Time",

    "RN1Time",
    "RN2Time",
    "RN3Time",

    "RF1Time",
    "RF2Time",
    "RF3Time",
]


# =========================================================
# NAME HELPER
# =========================================================

def _safe_name(
    run_number: int,
    group: str,
    quantity: str,
) -> str:

    value = (
        f"run_{run_number:05d}_"
        f"{group}_"
        f"{quantity}"
    )

    return re.sub(
        r"[^A-Za-z0-9_]+",
        "_",
        value,
    ).lower()


# =========================================================
# CREATE ONE QUANTITY SAFELY
# =========================================================

def _create_quantity_safely(
    dataframe,
    dataframe_label: str,
    quantity: str,
    run_number: int,
    group: str,
    group_title: str,
) -> tuple[
    str | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:

    try:

        # -------------------------------------------------
        # Create only ONE histogram
        # -------------------------------------------------

        histograms = (
            get_tram_histograms(
                dataframe=[
                    dataframe,
                ],
                dataframe_labels=[
                    dataframe_label,
                ],
                quantities=[
                    quantity,
                ],
            )
        )

        histogram = (
            histograms[
                quantity
            ][
                dataframe_label
            ]
        )


        # -------------------------------------------------
        # Plot one histogram
        #
        # 1D:
        #     canvas_info["canvas"]
        #
        # 2D:
        #     canvas_info["canvases_2d"]
        # -------------------------------------------------

        canvas_info = (
            plot_tram_histograms(
                histogram
            )
        )


        # =================================================
        # DETERMINE DIMENSION
        # =================================================

        is_2d = (
            hasattr(
                histogram,
                "InheritsFrom"
            )
            and histogram.InheritsFrom(
                "TH2"
            )
        )


        # =================================================
        # GET CANVAS
        # =================================================

        canvas = None


        # -------------------------------------------------
        # 1D histogram
        # -------------------------------------------------

        if not is_2d:

            canvas = (
                canvas_info.get(
                    "canvas"
                )
            )


        # -------------------------------------------------
        # 2D histogram
        # -------------------------------------------------

        else:

            canvases_2d = (
                canvas_info.get(
                    "canvases_2d",
                    [],
                )
            )

            # Normally there is exactly one canvas because
            # we passed exactly one quantity.
            if canvases_2d:

                canvas = (
                    canvases_2d[
                        0
                    ]
                )


        # -------------------------------------------------
        # Safety fallback
        # -------------------------------------------------

        if canvas is None:

            # Try 1D canvas first.
            canvas = (
                canvas_info.get(
                    "canvas"
                )
            )

        if canvas is None:

            # Then try first 2D canvas.
            canvases_2d = (
                canvas_info.get(
                    "canvases_2d",
                    [],
                )
            )

            if canvases_2d:

                canvas = (
                    canvases_2d[
                        0
                    ]
                )


        # -------------------------------------------------
        # Nothing produced
        # -------------------------------------------------

        if canvas is None:

            raise RuntimeError(
                f"No canvas produced "
                f"for {quantity}"
            )


        # =================================================
        # SAFE ROOT/WEB NAME
        # =================================================

        name = _safe_name(
            run_number,
            group,
            quantity,
        )


        # =================================================
        # RESULT
        # =================================================

        result = {
            "canvas":
                canvas,

            # Keep complete plotting structure alive.
            "canvas_info":
                canvas_info,

            "histogram":
                histogram,

            "quantity":
                quantity,

            "group":
                group,

            "group_title":
                group_title,

            "dimension":
                2
                if is_2d
                else 1,
        }


        return (
            name,
            result,
            None,
        )


    except Exception as error:

        print(
            f"[WARNING] "
            f"Scintillator quantity "
            f"'{quantity}' failed: "
            f"{error}"
        )


        failure = {
            "quantity":
                quantity,

            "group":
                group,

            "group_title":
                group_title,

            "error":
                str(error),
        }


        return (
            None,
            None,
            failure,
        )


# =========================================================
# PROCESS ONE GROUP
# =========================================================

def _process_group(
    dataframe,
    dataframe_label: str,
    quantities: list[str],
    run_number: int,
    group: str,
    group_title: str,
) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
]:

    results: dict[
        str,
        dict[str, Any]
    ] = {}

    failures: list[
        dict[str, Any]
    ] = []

    for quantity in quantities:

        (
            name,
            result,
            failure,
        ) = _create_quantity_safely(
            dataframe=(
                dataframe
            ),
            dataframe_label=(
                dataframe_label
            ),
            quantity=(
                quantity
            ),
            run_number=(
                run_number
            ),
            group=(
                group
            ),
            group_title=(
                group_title
            ),
        )

        if (
            name is not None
            and result is not None
        ):

            results[
                name
            ] = result

        if failure is not None:

            failures.append(
                failure
            )

    return (
        results,
        failures,
    )


# =========================================================
# MAIN
# =========================================================

def create_scintillator_diagnostics(
    root_files: list[Path],
    run_number: int,
    number_of_threads: int = 8,
) -> dict[str, Any]:

    if not root_files:

        raise RuntimeError(
            f"Run {run_number:05d} "
            f"has no ROOT files."
        )

    dataframe_label = (
        f"Run {run_number:05d}"
    )

    print()
    print("=" * 72)

    print(
        f"Creating scintillator diagnostics "
        f"for run {run_number:05d}"
    )

    print(
        f"ROOT files: "
        f"{len(root_files)}"
    )

    print("=" * 72)


    # =====================================================
    # RDATAFRAME
    # =====================================================

    rdataframe = (
        get_general_rdataframe(
            selected_files=(
                root_files
            ),
            tree_name=(
                "t2_clusters"
            ),
            number_of_threads=(
                number_of_threads
            ),
        )
    )


    all_results: dict[
        str,
        dict[str, Any]
    ] = {}

    all_failures: list[
        dict[str, Any]
    ] = []


    # =====================================================
    # 1. SCINTILLATOR ENERGY
    # =====================================================

    (
        results,
        failures,
    ) = _process_group(
        dataframe=(
            rdataframe
        ),
        dataframe_label=(
            dataframe_label
        ),
        quantities=(
            SCINTILLATOR_ENERGY_QUANTITIES
        ),
        run_number=(
            run_number
        ),
        group=(
            "scintillator_energy"
        ),
        group_title=(
            "Scintillator Energy"
        ),
    )

    all_results.update(
        results
    )

    all_failures.extend(
        failures
    )


    # =====================================================
    # 2. TRACKER SCINTILLATOR ENERGY
    # =====================================================

    (
        results,
        failures,
    ) = _process_group(
        dataframe=(
            rdataframe
        ),
        dataframe_label=(
            dataframe_label
        ),
        quantities=(
            TRACKER_SCINTILLATOR_ENERGY_QUANTITIES
        ),
        run_number=(
            run_number
        ),
        group=(
            "tracker_scintillator_energy"
        ),
        group_title=(
            "Tracker Scintillator Energy"
        ),
    )

    all_results.update(
        results
    )

    all_failures.extend(
        failures
    )


    # =====================================================
    # 3. SCINTILLATOR TIME
    # =====================================================

    (
        results,
        failures,
    ) = _process_group(
        dataframe=(
            rdataframe
        ),
        dataframe_label=(
            dataframe_label
        ),
        quantities=(
            SCINTILLATOR_TIME_QUANTITIES
        ),
        run_number=(
            run_number
        ),
        group=(
            "scintillator_time"
        ),
        group_title=(
            "Scintillator Time"
        ),
    )

    all_results.update(
        results
    )

    all_failures.extend(
        failures
    )


    # =====================================================
    # 4. TRACKER SCINTILLATOR TIME
    # =====================================================

    (
        results,
        failures,
    ) = _process_group(
        dataframe=(
            rdataframe
        ),
        dataframe_label=(
            dataframe_label
        ),
        quantities=(
            TRACKER_SCINTILLATOR_TIME_QUANTITIES
        ),
        run_number=(
            run_number
        ),
        group=(
            "tracker_scintillator_time"
        ),
        group_title=(
            "Tracker Scintillator Time"
        ),
    )

    all_results.update(
        results
    )

    all_failures.extend(
        failures
    )


    # =====================================================
    # SUMMARY
    # =====================================================

    print()
    print("=" * 72)

    print(
        f"Scintillator diagnostics completed "
        f"for run {run_number:05d}"
    )

    print(
        f"Successful plots : "
        f"{len(all_results)}"
    )

    print(
        f"Failed plots     : "
        f"{len(all_failures)}"
    )

    if all_failures:

        print()
        print(
            "Skipped scintillator plots:"
        )

        for failure in all_failures:

            print(
                f"  - "
                f"{failure['quantity']}: "
                f"{failure['error']}"
            )

    print("=" * 72)


    return {
        "results":
            all_results,

        "failures":
            all_failures,
    }