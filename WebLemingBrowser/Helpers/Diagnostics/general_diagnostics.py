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


GENERAL_DIAGNOSTICS_QUANTITIES = [
    "hasPileup",
    "pileupType",
    "tC61vsC62",
    "tC63vsC62",
]


TEMPERATURE_QUANTITIES = [
    "temp_50K",
    "temp_4K",
    "temp_still",
    "temp_MXC",
    "temp_LN2Bucket",
    "temp_si_strips",
    "temp_chamber",
]


RATE_QUANTITIES = [
    "rate1",
    "rate2",
    "rate3",
    "rate4",
]


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
    """
    Create exactly ONE histogram and ONE canvas.

    Supports both:
      - 1D ROOT histograms
      - 2D ROOT histograms

    Returns:
        (name, success_info, failure_info)
    """

    try:

        # -------------------------------------------------
        # One quantity only.
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
        # Exactly one plot input
        # -------------------------------------------------

        canvas_info = (
            plot_tram_histograms(
                histogram
            )
        )


        # =================================================
        # DETERMINE HISTOGRAM DIMENSION
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
        # GET CORRECT CANVAS
        # =================================================

        canvas = None


        # -------------------------------------------------
        # 1D
        # -------------------------------------------------

        if not is_2d:

            canvas = (
                canvas_info.get(
                    "canvas"
                )
            )


        # -------------------------------------------------
        # 2D
        # -------------------------------------------------

        else:

            canvases_2d = (
                canvas_info.get(
                    "canvases_2d",
                    [],
                )
            )

            if canvases_2d:

                # Since we supplied one quantity,
                # there should normally be one canvas.
                canvas = (
                    canvases_2d[
                        0
                    ]
                )


        # =================================================
        # FALLBACK
        # =================================================

        if canvas is None:

            canvas = (
                canvas_info.get(
                    "canvas"
                )
            )


        if canvas is None:

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


        # =================================================
        # NOTHING PRODUCED
        # =================================================

        if canvas is None:

            raise RuntimeError(
                f"No canvas returned "
                f"for {quantity}"
            )


        # =================================================
        # UNIQUE ROOT / WEB NAME
        # =================================================

        name = _safe_name(
            run_number,
            group,
            quantity,
        )


        # =================================================
        # SUCCESS RESULT
        # =================================================

        success = {
            "canvas":
                canvas,

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
                (
                    2
                    if is_2d
                    else 1
                ),
        }


        return (
            name,
            success,
            None,
        )


    except Exception as error:

        print(
            f"[WARNING] Diagnostic quantity "
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

    results = {}

    failures = []


    for quantity in quantities:

        (
            name,
            success,
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
            and success is not None
        ):

            results[
                name
            ] = success


        if failure is not None:

            failures.append(
                failure
            )


    return (
        results,
        failures,
    )


def create_general_diagnostics(
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


    all_results = {}

    all_failures = []


    print()
    print("=" * 72)

    print(
        f"Creating general diagnostics "
        f"for run {run_number:05d}"
    )

    print(
        f"ROOT files: "
        f"{len(root_files)}"
    )

    print("=" * 72)


    # =====================================================
    # 1. DIAGNOSTICS TREE
    # =====================================================

    try:

        diagnostics_rdf = (
            get_general_rdataframe(
                selected_files=(
                    root_files
                ),

                tree_name=(
                    "diagnostics"
                ),

                number_of_threads=(
                    number_of_threads
                ),
            )
        )


        (
            results,
            failures,
        ) = _process_group(
            dataframe=(
                diagnostics_rdf
            ),

            dataframe_label=(
                dataframe_label
            ),

            quantities=(
                GENERAL_DIAGNOSTICS_QUANTITIES
            ),

            run_number=(
                run_number
            ),

            group=(
                "general_diagnostics"
            ),

            group_title=(
                "Diagnostics"
            ),
        )


        all_results.update(
            results
        )

        all_failures.extend(
            failures
        )


    except Exception as error:

        print(
            f"[WARNING] Entire diagnostics tree "
            f"failed: {error}"
        )


        for quantity in (
            GENERAL_DIAGNOSTICS_QUANTITIES
        ):

            all_failures.append({
                "quantity":
                    quantity,

                "group":
                    "general_diagnostics",

                "group_title":
                    "Diagnostics",

                "error":
                    str(error),
            })


    # =====================================================
    # 2. TEMPERATURE TREE
    # =====================================================

    try:

        temperatures_rdf = (
            get_general_rdataframe(
                selected_files=(
                    root_files
                ),

                tree_name=(
                    "temperatures"
                ),

                number_of_threads=(
                    number_of_threads
                ),
            )
        )


        (
            results,
            failures,
        ) = _process_group(
            dataframe=(
                temperatures_rdf
            ),

            dataframe_label=(
                dataframe_label
            ),

            quantities=(
                TEMPERATURE_QUANTITIES
            ),

            run_number=(
                run_number
            ),

            group=(
                "temperatures"
            ),

            group_title=(
                "Temperatures"
            ),
        )


        all_results.update(
            results
        )

        all_failures.extend(
            failures
        )


    except Exception as error:

        print(
            f"[WARNING] Entire temperatures tree "
            f"failed: {error}"
        )


        for quantity in (
            TEMPERATURE_QUANTITIES
        ):

            all_failures.append({
                "quantity":
                    quantity,

                "group":
                    "temperatures",

                "group_title":
                    "Temperatures",

                "error":
                    str(error),
            })


    # =====================================================
    # 3. RATES TREE
    # =====================================================

    try:

        rates_rdf = (
            get_general_rdataframe(
                selected_files=(
                    root_files
                ),

                tree_name=(
                    "rates"
                ),

                number_of_threads=(
                    number_of_threads
                ),
            )
        )


        (
            results,
            failures,
        ) = _process_group(
            dataframe=(
                rates_rdf
            ),

            dataframe_label=(
                dataframe_label
            ),

            quantities=(
                RATE_QUANTITIES
            ),

            run_number=(
                run_number
            ),

            group=(
                "rates"
            ),

            group_title=(
                "Rates"
            ),
        )


        all_results.update(
            results
        )

        all_failures.extend(
            failures
        )


    except Exception as error:

        print(
            f"[WARNING] Entire rates tree "
            f"failed: {error}"
        )


        for quantity in (
            RATE_QUANTITIES
        ):

            all_failures.append({
                "quantity":
                    quantity,

                "group":
                    "rates",

                "group_title":
                    "Rates",

                "error":
                    str(error),
            })


    # =====================================================
    # SUMMARY
    # =====================================================

    print()
    print("=" * 72)

    print(
        f"General diagnostics completed "
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

    print("=" * 72)


    return {
        "results":
            all_results,

        "failures":
            all_failures,
    }