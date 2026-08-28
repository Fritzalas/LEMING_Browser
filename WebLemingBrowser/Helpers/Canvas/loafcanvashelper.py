import math
import time
from typing import Any
import ROOT
import re
import os
import sys
# getting the name of the directory
# where this file is present.
current = os.path.dirname(
    os.path.realpath(__file__)
)
# Getting the parent directory name.
parent = os.path.dirname(
    current
)
# adding the parent directory to sys.path.
if parent not in sys.path:
    sys.path.append(
        parent
    )

from Classes.LoafQuantitySpec import LoafQuantitySpec

def create_1D_loaf_canvas(
    histogram_data: list[dict[str, Any]],
    quantities: list[str],
    show_provenance: bool,
    title: str | None,
    x_axis_title: str | None,
    y_axis_title: str | None,
):
    """
    *************** Depracated Function Because Now everything is in tram files *********************
    Create the 1D LOAF histogram canvas.

    When show_provenance=True:
        - histogram plots are shown on the left
        - provenance is shown on the right
        - both are part of the same ROOT TCanvas
        - the provenance image is generated at the exact pixel
          dimensions required by the provenance pad
    """

    if not histogram_data:
        return None

    quantity_count = len(
        quantities
    )

    if quantity_count == 0:
        return None

    number_of_columns = min(
        quantity_count,
        3,
    )

    number_of_rows = math.ceil(
        quantity_count
        / number_of_columns
    )

    canvas_name = (
        f"c_loaf_{time.time_ns()}"
    )

    # ---------------------------------------------------------
    # Canvas layout
    # ---------------------------------------------------------

    layout = _get_canvas_layout(
        number_of_histogram_columns=number_of_columns,
        number_of_histogram_rows=number_of_rows,
        show_provenance=show_provenance,
    )

    canvas_width = int(
        layout[
            "canvas_width"
        ]
    )

    canvas_height = int(
        layout[
            "canvas_height"
        ]
    )

    histogram_fraction = float(
        layout[
            "histogram_fraction"
        ]
    )

    # ---------------------------------------------------------
    # Calculate provenance pixel dimensions
    # ---------------------------------------------------------

    provenance_pixel_width = 0
    provenance_pixel_height = 0

    if show_provenance:
        provenance_pixel_width = max(
            1,
            int(
                canvas_width
                * (
                    1.0
                    - histogram_fraction
                )
            ),
        )

        provenance_pixel_height = max(
            1,
            canvas_height,
        )

    # ---------------------------------------------------------
    # Prepare provenance image
    # ---------------------------------------------------------

    provenance_image = None
    provenance_path = None

    # ---------------------------------------------------------
    # Canvas
    # ---------------------------------------------------------

    canvas = ROOT.TCanvas(
        canvas_name,
        title or "loaf distributions",
        canvas_width,
        canvas_height,
    )

    # ---------------------------------------------------------
    # Main layout
    # ---------------------------------------------------------

    if show_provenance:
        histogram_pad = ROOT.TPad(
            f"{canvas_name}_histograms",
            "Histograms",
            0.0,
            0.0,
            histogram_fraction,
            1.0,
        )

        provenance_pad = ROOT.TPad(
            f"{canvas_name}_provenance",
            "Provenance",
            histogram_fraction,
            0.0,
            1.0,
            1.0,
        )

        histogram_pad.SetRightMargin(
            0.01
        )

        provenance_pad.SetLeftMargin(
            0.0
        )

        provenance_pad.SetRightMargin(
            0.0
        )

        provenance_pad.SetTopMargin(
            0.0
        )

        provenance_pad.SetBottomMargin(
            0.0
        )

        histogram_pad.Draw()
        provenance_pad.Draw()

        histogram_pad.cd()

        histogram_pad.Divide(
            number_of_columns,
            number_of_rows,
            0.001,
            0.001,
        )

    else:
        histogram_pad = canvas
        provenance_pad = None

        canvas.Divide(
            number_of_columns,
            number_of_rows,
            0.001,
            0.001,
        )

    # ---------------------------------------------------------
    # Styling
    # ---------------------------------------------------------

    root_colors = [
        ROOT.kBlue + 1,
        ROOT.kRed + 1,
        ROOT.kGreen + 2,
        ROOT.kMagenta + 1,
        ROOT.kOrange + 7,
        ROOT.kCyan + 1,
        ROOT.kViolet + 1,
        ROOT.kBlack,
    ]

    legends = []
    drawn_histograms = []

    histogram_lookup: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for item in histogram_data:
        histogram_lookup.setdefault(
            item["quantity"],
            [],
        ).append(
            item
        )

    # ---------------------------------------------------------
    # Draw histograms
    # ---------------------------------------------------------

    for pad_index, quantity in enumerate(
        quantities,
        start=1,
    ):
        histogram_pad.cd(
            pad_index
        )

        ROOT.gPad.SetGrid()

        ROOT.gPad.SetTicks(
            1,
            1,
        )

        ROOT.gPad.SetLeftMargin(
            0.12
        )

        ROOT.gPad.SetRightMargin(
            0.04
        )

        ROOT.gPad.SetTopMargin(
            0.10
        )

        ROOT.gPad.SetBottomMargin(
            0.12
        )

        items = histogram_lookup.get(
            quantity,
            [],
        )

        if not items:
            continue

        default_y_axis_title = (
            "Normalized entries"
            if items[0].get(
                "normalized",
                False,
            )
            else "Entries"
        )

        pad_title = (
            title
            if title is not None
            else f"{quantity} Distribution"
        )

        pad_x_axis_title = (
            x_axis_title
            if x_axis_title is not None
            else quantity
        )

        pad_y_axis_title = (
            y_axis_title
            if y_axis_title is not None
            else default_y_axis_title
        )

        legend = ROOT.TLegend(
            0.68,
            0.73,
            0.94,
            0.90,
        )

        legend.SetBorderSize(
            0
        )

        legend.SetFillStyle(
            0
        )

        legend.SetTextSize(
            0.035
        )

        maximum_bin_content = max(
            item[
                "histogram"
            ].GetMaximum()
            for item in items
        )

        y_axis_maximum = (
            maximum_bin_content
            * 1.15
            if maximum_bin_content > 0
            else 1.0
        )

        for dataset_index, item in enumerate(
            items
        ):
            histogram = item[
                "histogram"
            ]

            color = root_colors[
                dataset_index
                % len(
                    root_colors
                )
            ]

            histogram.SetLineColor(
                color
            )

            histogram.SetMarkerColor(
                color
            )

            histogram.SetLineWidth(
                2
            )

            histogram.SetMarkerStyle(
                8
            )

            histogram.SetMarkerSize(
                0.65
            )

            histogram.SetStats(
                True
            )

            histogram.GetXaxis().SetTitleSize(
                0.040
            )

            histogram.GetYaxis().SetTitleSize(
                0.040
            )

            histogram.GetXaxis().SetLabelSize(
                0.032
            )

            histogram.GetYaxis().SetLabelSize(
                0.032
            )

            histogram.GetXaxis().SetTitleOffset(
                1.15
            )

            histogram.GetYaxis().SetTitleOffset(
                1.35
            )

            if dataset_index == 0:
                histogram.SetTitle(
                    f"{pad_title};"
                    f"{pad_x_axis_title};"
                    f"{pad_y_axis_title}"
                )

                histogram.GetYaxis().SetRangeUser(
                    0.00001,
                    y_axis_maximum,
                )

                histogram.Draw(
                    "HIST"
                )

                histogram.Draw(
                    "E SAME"
                )

            else:
                histogram.Draw(
                    "HIST SAME"
                )

                histogram.Draw(
                    "E SAME"
                )

            legend.AddEntry(
                histogram,
                item[
                    "dataset_label"
                ],
                "lep",
            )

            drawn_histograms.append(
                histogram
            )

        legend.Draw()

        legends.append(
            legend
        )

    # ---------------------------------------------------------
    # Draw provenance
    # ---------------------------------------------------------

    if (
        show_provenance
        and provenance_pad is not None
        and provenance_image is not None
    ):
        _draw_provenance_image(
            pad=provenance_pad,
            provenance_image=provenance_image,
        )

    # ---------------------------------------------------------
    # Final canvas
    # ---------------------------------------------------------

    canvas.cd()
    canvas.Modified()
    canvas.Update()

    return {
        "canvas": canvas,
        "canvas_name": canvas_name,

        "histogram_pad": histogram_pad,
        "provenance_pad": provenance_pad,

        "legends": legends,
        "drawn_histograms": drawn_histograms,

        # Keep PyROOT image alive.
        "provenance_image": (
            provenance_image
        ),

        "provenance_path": (
            provenance_path
        ),

        # Layout metadata.
        "canvas_width": (
            canvas_width
        ),

        "canvas_height": (
            canvas_height
        ),

        "histogram_fraction": (
            histogram_fraction
        ),

        "provenance_pixel_width": (
            provenance_pixel_width
        ),

        "provenance_pixel_height": (
            provenance_pixel_height
        ),
    }


def create_loaf_2d_canvases(
    histogram_data: list[dict[str, Any]],
    quantity_specs: list[LoafQuantitySpec],
    show_3d: bool,
    show_provenance: bool,
) -> list[dict[str, Any]]:
    """
    *************** Depracated Function Because Now everything is in tram files *********************
    Create one separate canvas for each 2D expression.

    If show_provenance=True:
        - the provenance graph is displayed on the right
        - provenance is rendered specifically for the available
          provenance-pad resolution

    If show_3d=True:
        - an additional LEGO2 canvas is created
        - the same provenance image is reused
    """

    canvas_data: list[
        dict[str, Any]
    ] = []

    for spec in quantity_specs:
        if spec.dimension != 2:
            continue

        expression_items = [
            item
            for item in histogram_data
            if (
                item["expression"]
                == spec.expression
            )
        ]

        if not expression_items:
            continue

        dataframe_count = len(
            expression_items
        )

        number_of_columns = min(
            dataframe_count,
            3,
        )

        number_of_rows = math.ceil(
            dataframe_count
            / number_of_columns
        )

        safe_expression = (
            _make_safe_root_name(
                spec.expression
            )
        )

        # -----------------------------------------------------
        # Canvas layout
        # -----------------------------------------------------

        layout = _get_2d_canvas_layout(
            number_of_histogram_columns=(
                number_of_columns
            ),
            number_of_histogram_rows=(
                number_of_rows
            ),
            show_provenance=(
                show_provenance
            ),
        )

        canvas_width = int(
            layout[
                "canvas_width"
            ]
        )

        canvas_height = int(
            layout[
                "canvas_height"
            ]
        )

        histogram_fraction = float(
            layout[
                "histogram_fraction"
            ]
        )

        # -----------------------------------------------------
        # Provenance pixel size
        # -----------------------------------------------------

        provenance_pixel_width = 0
        provenance_pixel_height = 0

        if show_provenance:
            provenance_pixel_width = max(
                1,
                int(
                    canvas_width
                    * (
                        1.0
                        - histogram_fraction
                    )
                ),
            )

            provenance_pixel_height = max(
                1,
                canvas_height,
            )

        # -----------------------------------------------------
        # Prepare provenance
        # -----------------------------------------------------

        provenance_image = None
        provenance_path = None

        # =====================================================
        # COLZ canvas
        # =====================================================

        canvas_name = (
            f"c_loaf_2d_"
            f"{safe_expression}_"
            f"{time.time_ns()}"
        )

        canvas = ROOT.TCanvas(
            canvas_name,
            spec.title,
            canvas_width,
            canvas_height,
        )

        # -----------------------------------------------------
        # COLZ layout
        # -----------------------------------------------------

        if show_provenance:
            histogram_pad = ROOT.TPad(
                f"{canvas_name}_histograms",
                "Histograms",
                0.0,
                0.0,
                histogram_fraction,
                1.0,
            )

            provenance_pad = ROOT.TPad(
                f"{canvas_name}_provenance",
                "Provenance",
                histogram_fraction,
                0.0,
                1.0,
                1.0,
            )

            histogram_pad.SetRightMargin(
                0.01
            )

            provenance_pad.SetLeftMargin(
                0.0
            )

            provenance_pad.SetRightMargin(
                0.0
            )

            provenance_pad.SetTopMargin(
                0.0
            )

            provenance_pad.SetBottomMargin(
                0.0
            )

            histogram_pad.Draw()
            provenance_pad.Draw()

            histogram_pad.cd()

            histogram_pad.Divide(
                number_of_columns,
                number_of_rows,
                0.001,
                0.001,
            )

        else:
            histogram_pad = canvas
            provenance_pad = None

            canvas.Divide(
                number_of_columns,
                number_of_rows,
                0.001,
                0.001,
            )

        # -----------------------------------------------------
        # Draw COLZ histograms
        # -----------------------------------------------------

        drawn_histograms = []

        for pad_index, item in enumerate(
            expression_items,
            start=1,
        ):
            histogram_pad.cd(
                pad_index
            )

            ROOT.gPad.SetGrid()

            ROOT.gPad.SetTicks(
                1,
                1,
            )

            ROOT.gPad.SetLeftMargin(
                0.13
            )

            # Leave enough room for COLZ palette.
            ROOT.gPad.SetRightMargin(
                0.14
            )

            ROOT.gPad.SetTopMargin(
                0.09
            )

            ROOT.gPad.SetBottomMargin(
                0.13
            )

            histogram = item[
                "histogram"
            ]

            histogram.SetStats(
                True
            )

            histogram.SetTitle(
                f"{item['dataset_label']} - "
                f"{spec.y_column} versus "
                f"{spec.x_column};"
                f"{spec.x_column};"
                f"{spec.y_column}"
            )

            histogram.GetXaxis().SetTitleSize(
                0.036
            )

            histogram.GetYaxis().SetTitleSize(
                0.036
            )

            histogram.GetXaxis().SetLabelSize(
                0.029
            )

            histogram.GetYaxis().SetLabelSize(
                0.029
            )

            histogram.GetXaxis().SetTitleOffset(
                1.20
            )

            histogram.GetYaxis().SetTitleOffset(
                1.45
            )

            histogram.Draw(
                "COLZ"
            )

            drawn_histograms.append(
                histogram
            )

        # -----------------------------------------------------
        # Draw provenance
        # -----------------------------------------------------

        if (
            show_provenance
            and provenance_pad
            is not None
            and provenance_image
            is not None
        ):
            _draw_provenance_image(
                pad=provenance_pad,
                provenance_image=(
                    provenance_image
                ),
            )

        canvas.cd()
        canvas.Modified()
        canvas.Update()

        # =====================================================
        # Optional 3D canvas
        # =====================================================

        canvas_3d = None
        canvas_name_3d = None

        histogram_pad_3d = None
        provenance_pad_3d = None

        drawn_histograms_3d = []

        if show_3d:
            canvas_name_3d = (
                f"c_loaf_2d_3d_"
                f"{safe_expression}_"
                f"{time.time_ns()}"
            )

            canvas_3d = ROOT.TCanvas(
                canvas_name_3d,
                f"{spec.title} - 3D",
                canvas_width,
                canvas_height,
            )

            # -------------------------------------------------
            # 3D layout
            # -------------------------------------------------

            if show_provenance:
                histogram_pad_3d = (
                    ROOT.TPad(
                        (
                            f"{canvas_name_3d}"
                            "_histograms"
                        ),
                        "Histograms",
                        0.0,
                        0.0,
                        histogram_fraction,
                        1.0,
                    )
                )

                provenance_pad_3d = (
                    ROOT.TPad(
                        (
                            f"{canvas_name_3d}"
                            "_provenance"
                        ),
                        "Provenance",
                        histogram_fraction,
                        0.0,
                        1.0,
                        1.0,
                    )
                )

                histogram_pad_3d.SetRightMargin(
                    0.01
                )

                provenance_pad_3d.SetLeftMargin(
                    0.0
                )

                provenance_pad_3d.SetRightMargin(
                    0.0
                )

                provenance_pad_3d.SetTopMargin(
                    0.0
                )

                provenance_pad_3d.SetBottomMargin(
                    0.0
                )

                histogram_pad_3d.Draw()
                provenance_pad_3d.Draw()

                histogram_pad_3d.cd()

                histogram_pad_3d.Divide(
                    number_of_columns,
                    number_of_rows,
                    0.001,
                    0.001,
                )

            else:
                histogram_pad_3d = (
                    canvas_3d
                )

                provenance_pad_3d = None

                canvas_3d.Divide(
                    number_of_columns,
                    number_of_rows,
                    0.001,
                    0.001,
                )

            # -------------------------------------------------
            # Draw LEGO2 histograms
            # -------------------------------------------------

            for pad_index, item in enumerate(
                expression_items,
                start=1,
            ):
                histogram_pad_3d.cd(
                    pad_index
                )

                ROOT.gPad.SetGrid()

                ROOT.gPad.SetTicks(
                    1,
                    1,
                )

                ROOT.gPad.SetLeftMargin(
                    0.12
                )

                ROOT.gPad.SetRightMargin(
                    0.08
                )

                ROOT.gPad.SetTopMargin(
                    0.10
                )

                ROOT.gPad.SetBottomMargin(
                    0.12
                )

                histogram = item[
                    "histogram"
                ]

                histogram.SetStats(
                    True
                )

                histogram.SetTitle(
                    f"{item['dataset_label']} - "
                    f"{spec.y_column} versus "
                    f"{spec.x_column};"
                    f"{spec.x_column};"
                    f"{spec.y_column};"
                    "Counts"
                )

                histogram.GetXaxis().SetTitleSize(
                    0.040
                )

                histogram.GetYaxis().SetTitleSize(
                    0.040
                )

                histogram.GetZaxis().SetTitleSize(
                    0.040
                )

                histogram.GetXaxis().SetLabelSize(
                    0.032
                )

                histogram.GetYaxis().SetLabelSize(
                    0.032
                )

                histogram.GetZaxis().SetLabelSize(
                    0.032
                )

                histogram.Draw(
                    "LEGO2"
                )

                drawn_histograms_3d.append(
                    histogram
                )

            # -------------------------------------------------
            # Provenance in 3D canvas
            # -------------------------------------------------

            if (
                show_provenance
                and provenance_pad_3d
                is not None
                and provenance_image
                is not None
            ):
                _draw_provenance_image(
                    pad=provenance_pad_3d,
                    provenance_image=(
                        provenance_image
                    ),
                )

            canvas_3d.cd()
            canvas_3d.Modified()
            canvas_3d.Update()

        # =====================================================
        # Metadata
        # =====================================================

        canvas_data.append({
            # COLZ
            "canvas": canvas,
            "canvas_name": canvas_name,

            "histogram_pad": (
                histogram_pad
            ),

            "provenance_pad": (
                provenance_pad
            ),

            "drawn_histograms": (
                drawn_histograms
            ),

            # 3D
            "canvas_3d": (
                canvas_3d
            ),

            "canvas_name_3d": (
                canvas_name_3d
            ),

            "histogram_pad_3d": (
                histogram_pad_3d
            ),

            "provenance_pad_3d": (
                provenance_pad_3d
            ),

            "drawn_histograms_3d": (
                drawn_histograms_3d
            ),

            # Provenance
            "provenance_image": (
                provenance_image
            ),

            "provenance_path": (
                provenance_path
            ),

            # Layout
            "canvas_width": (
                canvas_width
            ),

            "canvas_height": (
                canvas_height
            ),

            "histogram_fraction": (
                histogram_fraction
            ),

            "provenance_pixel_width": (
                provenance_pixel_width
            ),

            "provenance_pixel_height": (
                provenance_pixel_height
            ),

            # Common metadata
            "expression": (
                spec.expression
            ),

            "spec": spec,
            "legends": [],
        })

    return canvas_data

def _draw_provenance_image(
    pad,
    provenance_image,
) -> None:
    """
    Draw the already correctly-sized provenance image into a pad.

    Because the PNG is generated at approximately the same pixel
    dimensions as this pad, ROOT has very little rescaling to do.
    """

    pad.cd()

    pad.SetFillColor(
        ROOT.kWhite
    )

    pad.SetLeftMargin(
        0.0
    )

    pad.SetRightMargin(
        0.0
    )

    pad.SetTopMargin(
        0.0
    )

    pad.SetBottomMargin(
        0.0
    )

    provenance_image.Draw(
        "xxx"
    )

    pad.Modified()
    pad.Update()


def _make_safe_root_name(
    value: str,
) -> str:
    """
    Convert a string into a safe ROOT object name.
    """

    safe_name = re.sub(
        pattern=r"[^A-Za-z0-9_]",
        repl="_",
        string=value,
    )

    safe_name = (
        safe_name.strip(
            "_"
        )
    )

    return (
        safe_name
        or "object"
    )


def _get_canvas_layout(
    number_of_histogram_columns: int,
    number_of_histogram_rows: int,
    show_provenance: bool,
) -> dict[str, int | float]:
    """
    Layout for 1D histogram canvases.
    """

    base_width = max(
        900,
        480
        * number_of_histogram_columns,
    )

    base_height = max(
        650,
        420
        * number_of_histogram_rows,
    )

    base_width = min(
        base_width,
        1450,
    )

    base_height = min(
        base_height,
        900,
    )

    if not show_provenance:
        return {
            "canvas_width": (
                base_width
            ),
            "canvas_height": (
                base_height
            ),
            "histogram_fraction": (
                1.0
            ),
        }

    canvas_width = min(
        max(
            base_width + 650,
            1450,
        ),
        1750,
    )

    canvas_height = (
        base_height
    )

    if number_of_histogram_columns == 1:
        histogram_fraction = 0.56

    elif number_of_histogram_columns == 2:
        histogram_fraction = 0.60

    else:
        histogram_fraction = 0.64

    return {
        "canvas_width": (
            canvas_width
        ),
        "canvas_height": (
            canvas_height
        ),
        "histogram_fraction": (
            histogram_fraction
        ),
    }


def _get_2d_canvas_layout(
    number_of_histogram_columns: int,
    number_of_histogram_rows: int,
    show_provenance: bool,
) -> dict[str, int | float]:
    """
    Layout specifically tuned for COLZ / LEGO2 plots.

    2D histograms are allocated slightly more horizontal space
    because COLZ also needs room for the palette.
    """

    base_width = max(
        900,
        560
        * number_of_histogram_columns,
    )

    base_height = max(
        680,
        460
        * number_of_histogram_rows,
    )

    base_width = min(
        base_width,
        1450,
    )

    base_height = min(
        base_height,
        900,
    )

    if not show_provenance:
        return {
            "canvas_width": (
                base_width
            ),
            "canvas_height": (
                base_height
            ),
            "histogram_fraction": (
                1.0
            ),
        }

    canvas_width = min(
        max(
            base_width + 600,
            1500,
        ),
        1750,
    )

    canvas_height = (
        base_height
    )

    if number_of_histogram_columns == 1:
        histogram_fraction = 0.62

    elif number_of_histogram_columns == 2:
        histogram_fraction = 0.65

    else:
        histogram_fraction = 0.68

    return {
        "canvas_width": (
            canvas_width
        ),
        "canvas_height": (
            canvas_height
        ),
        "histogram_fraction": (
            histogram_fraction
        ),
    }