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

from Helpers.Coincidence.tram_straight_coincidence import (
    apply_tram_straight_coincidence
)

from Helpers.Filter.general_apply_filter import (
    apply_global_filter,
)


# =========================================================
# QUANTITIES
# =========================================================

CLUSTER_X_QUANTITIES = [
    "x1L",
    "x2L",
    "x1R",
    "x2R",
]

CLUSTER_Y_QUANTITIES = [
    "Y1L",
    "Y2L",
    "Y1R",
    "Y2R",
]


CLUSTER_Z_QUANTITIES = [
    "Z1L",
    "Z2L",
    "Z1R",
    "Z2R",
]


HITMAP_QUANTITIES = [
    "Y1L:Z1L",
    "Y1R:Z1R",
    "Y2L:Z2L",
    "Y2R:Z2R",
]


EDEP_Z_QUANTITIES = [
    "edep_Z1L",
    "edep_Z2L",
    "edep_Z1R",
    "edep_Z2R",
]


EDEP_Y_QUANTITIES = [
    "edep_Y1L",
    "edep_Y2L",
    "edep_Y1R",
    "edep_Y2R",
]


SIMPLE_STRAIGHT_COINCIDENCE_QUANTITIES = [
    "Z1L",
    "Z1R",
]


TRAM_STRAIGHT_COINCIDENCE_QUANTITIES = [
    "StraightZ1L",
    "StraightZ2L",
    "StraightZ1R",
    "StraightZ2R",
]


# =========================================================
# STRAIGHT COINCIDENCE SETTINGS
# =========================================================

STRAIGHT_COINCIDENCE_SETTINGS = {

    "delta_z_max_left": 0.2,
    "delta_z_max_right": 0.2,

    "z1_min_left": 0.0,
    "z1_max_left": 40.0,

    "z2_min_left": 0.0,
    "z2_max_left": 40.0,

    "z1_edep_min_left": None,
    "z1_edep_max_left": None,

    "z2_edep_min_left": None,
    "z2_edep_max_left": None,

    "z1_time_min_left": None,
    "z1_time_max_left": None,

    "z2_time_min_left": None,
    "z2_time_max_left": None,

    "z1_min_right": 0.0,
    "z1_max_right": 40.0,

    "z2_min_right": 0.0,
    "z2_max_right": 40.0,

    "z1_edep_min_right": None,
    "z1_edep_max_right": None,

    "z2_edep_min_right": None,
    "z2_edep_max_right": None,

    "z1_time_min_right": None,
    "z1_time_max_right": None,

    "z2_time_min_right": None,
    "z2_time_max_right": None,
}


# =========================================================
# NAME
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
# ONE QUANTITY
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

        canvas_info = (
            plot_tram_histograms(
                histogram
            )
        )

        # =================================================
        # 1D
        # =================================================

        canvas = (
            canvas_info.get(
                "canvas"
            )
        )


        # =================================================
        # 2D
        #
        # plot_tram_histograms() stores 2D canvases in
        # "canvases_2d", not in "canvas".
        # =================================================

        if canvas is None:

            canvases_2d = (
                canvas_info.get(
                    "canvases_2d",
                    [],
                )
            )

            if canvases_2d:

                canvas = (
                    canvases_2d[0]
                )


        # =================================================
        # Nothing produced
        # =================================================

        if canvas is None:

            raise RuntimeError(
                f"No canvas produced "
                f"for {quantity}"
            )


        name = _safe_name(
            run_number,
            group,
            quantity,
        )


        result = {
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
                    if histogram.InheritsFrom(
                        "TH2"
                    )
                    else 1
                ),
        }


        return (
            name,
            result,
            None,
        )


    except Exception as error:

        print(
            f"[WARNING] "
            f"Strip diagnostic quantity "
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
# GROUP
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

    results = {}
    failures = []

    for quantity in quantities:

        (
            name,
            result,
            failure,
        ) = _create_quantity_safely(
            dataframe=dataframe,
            dataframe_label=dataframe_label,
            quantity=quantity,
            run_number=run_number,
            group=group,
            group_title=group_title,
        )

        if (
            name is not None
            and result is not None
        ):
            results[name] = result

        if failure is not None:
            failures.append(
                failure
            )

    return (
        results,
        failures,
    )


# =========================================================
# SAFE FILTERED GROUP
# =========================================================

def _process_filtered_group(
    create_dataframe,
    dataframe_label: str,
    quantities: list[str],
    run_number: int,
    group: str,
    group_title: str,
) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
]:

    try:

        dataframe = (
            create_dataframe()
        )

    except Exception as error:

        print(
            f"[WARNING] "
            f"Could not create dataframe for "
            f"'{group_title}': {error}"
        )

        return (
            {},
            [
                {
                    "quantity":
                        quantity,

                    "group":
                        group,

                    "group_title":
                        group_title,

                    "error":
                        str(error),
                }

                for quantity in quantities
            ],
        )

    return _process_group(
        dataframe=dataframe,
        dataframe_label=dataframe_label,
        quantities=quantities,
        run_number=run_number,
        group=group,
        group_title=group_title,
    )


# =========================================================
# MAIN
# =========================================================

def create_strip_diagnostics(
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
        f"Creating strip diagnostics "
        f"for run {run_number:05d}"
    )

    print(
        f"ROOT files: {len(root_files)}"
    )

    print("=" * 72)


    # =====================================================
    # BASE t2_clusters DATAFRAME
    # =====================================================

    rdataframe = (
        get_general_rdataframe(
            selected_files=root_files,
            tree_name="t2_clusters",
            number_of_threads=(
                number_of_threads
            ),
        )
    )


    all_results = {}
    all_failures = []


    # =====================================================
    # NORMAL GROUPS
    # =====================================================

    groups = [
        (
            CLUSTER_Y_QUANTITIES,
            "cluster_y",
            "Y Strip Positions",
        ),

        (
            CLUSTER_X_QUANTITIES,
            "cluster_x",
            "X Strip Positions"
        ),

        (
            CLUSTER_Z_QUANTITIES,
            "cluster_z",
            "Z Strip Positions",
        ),

        (
            HITMAP_QUANTITIES,
            "hitmaps",
            "Strip Hitmaps",
        ),

        (
            EDEP_Z_QUANTITIES,
            "edep_z",
            "Z Strip Energy Deposits",
        ),

        (
            EDEP_Y_QUANTITIES,
            "edep_y",
            "Y Strip Energy Deposits",
        ),
    ]


    for (
        quantities,
        group,
        group_title,
    ) in groups:

        (
            results,
            failures,
        ) = _process_group(
            dataframe=rdataframe,
            dataframe_label=dataframe_label,
            quantities=quantities,
            run_number=run_number,
            group=group,
            group_title=group_title,
        )

        all_results.update(
            results
        )

        all_failures.extend(
            failures
        )


    # =====================================================
    # SIMPLE STRAIGHT COINCIDENCE
    # =====================================================

    (
        results,
        failures,
    ) = _process_filtered_group(
        create_dataframe=lambda:
            apply_global_filter(
                rdataframe,
                (
                    "(abs(Z1L-Z2L) < 0.2) || "
                    "(abs(Z1R-Z2R) < 0.2)"
                ),
            ),

        dataframe_label=dataframe_label,

        quantities=(
            SIMPLE_STRAIGHT_COINCIDENCE_QUANTITIES
        ),

        run_number=run_number,

        group=(
            "straight_coincidence"
        ),

        group_title=(
            "Straight Coincidence"
        ),
    )

    all_results.update(
        results
    )

    all_failures.extend(
        failures
    )


    # =====================================================
    # TRAM STRAIGHT COINCIDENCE
    # =====================================================

    (
        results,
        failures,
    ) = _process_filtered_group(
        create_dataframe=lambda:
            apply_tram_straight_coincidence(
                dataframes=(
                    rdataframe
                ),
                settings=(
                    STRAIGHT_COINCIDENCE_SETTINGS
                ),
            ),

        dataframe_label=dataframe_label,

        quantities=(
            TRAM_STRAIGHT_COINCIDENCE_QUANTITIES
        ),

        run_number=run_number,

        group=(
            "tram_straight_coincidence"
        ),

        group_title=(
            "TRAM Straight Coincidence"
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
        f"Strip diagnostics completed "
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
            "Skipped strip plots:"
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