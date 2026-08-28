from pathlib import Path
from typing import Any, Iterable
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from Canvas.loafcanvashelper import (
    create_1D_loaf_canvas,
    create_loaf_2d_canvases,
)
from Classes.LoafQuantitySpec import LoafQuantitySpec
from Exceptions.PlotCreationError import PlotCreationError

############################################################################
############### Deprecated Function with the new tram files ################
############################################################################

# ------------------------------------------------------------------
# Plotting pipeline
#
# plot_loaf_histo(...)
#     │
#     ▼
# _validate_and_normalize_histograms()
#     ├── Validate function arguments.
#     ├── Validate histogram dictionary structure.
#     ├── Validate ROOT histogram objects.
#     ├── Parse each quantity exactly once.
#     ├── Validate 1D quantities against TH1 histograms.
#     └── Validate 2D quantities against TH2 histograms.
#
# After this point, all inputs are guaranteed to be valid.
#
#     ▼
# _build_histogram_metadata()
#     ├── No quantity parsing.
#     ├── No input validation.
#     └── No histogram dimension checks.
#     │
#     ├───────────────┐
#     ▼               ▼
# _build_1d...   _build_2d...
#     │               │
#     └───────┬───────┘
#             ▼
#       Canvas helper functions
# ------------------------------------------------------------------

def plot_loaf_histograms(
    histograms: Any,
    quantity: str | None = None,
    dataframe_label: str = "DataFrame1",
    title: str | None = None,
    x_axis_title: str | None = None,
    y_axis_title: str | None = None,
    saveCanvas: bool = False,
    outputFileName: str | Path | None = None,
    outputFormats: str | Iterable[str] = None,
    show_3d: bool = False,
    show_provenance: bool = False
) -> dict[str, Any]:
    ############################################################################
    ############### Deprecated Function with the new tram files ################
    ############################################################################
    canvas_info = plot_loaf_histo(
        histograms=histograms,
        quantity=quantity,
        dataframe_label=dataframe_label,
        title = title,
        x_axis_title=x_axis_title,
        y_axis_title=y_axis_title,
        saveCanvas=saveCanvas,
        outputFileName=outputFileName,
        outputFormats=outputFormats,
        show_3d=show_3d,
        show_provenance=show_provenance
    )
    return canvas_info

def plot_loaf_histo(
    histograms: Any,
    quantity: str | None,
    dataframe_label: str,
    title: str | None,
    x_axis_title: str | None,
    y_axis_title: str | None,
    saveCanvas: bool,
    outputFileName: str | Path | None,
    outputFormats: str | Iterable[str],
    show_3d: bool,
    show_provenance: bool,
) -> dict[str, Any]:
    """
    Plot already-created Loaf ROOT histograms.
    """
    histogram_data_1d, histogram_data_2d = (
        _validate_and_normalize_histograms(
            histograms=histograms,
            quantity=quantity,
            dataframe_label=dataframe_label,
        )
    )

    # ------------------------------------------------------------
    # 1D
    # ------------------------------------------------------------

    canvas_result_1d = None

    if histogram_data_1d:
        quantities = list(
            dict.fromkeys(
                item["quantity"]
                for item in histogram_data_1d
            )
        )

        canvas_result_1d = create_1D_loaf_canvas(
            histogram_data=histogram_data_1d,
            quantities=quantities,
            title=title,
            x_axis_title=x_axis_title,
            y_axis_title=y_axis_title,
            show_provenance=show_provenance
        )

    if canvas_result_1d is None:
        canvas_1d = None
        canvas_name_1d = None
        legends_1d = []
        drawn_histograms_1d = []

    else:
        canvas_1d = (
            canvas_result_1d["canvas"]
        )

        canvas_name_1d = (
            canvas_result_1d["canvas_name"]
        )

        legends_1d = (
            canvas_result_1d["legends"]
        )

        drawn_histograms_1d = (
            canvas_result_1d[
                "drawn_histograms"
            ]
        )

    # ------------------------------------------------------------
    # 2D
    # ------------------------------------------------------------

    canvas_data_2d: list[dict[str, Any]] = []

    if histogram_data_2d:
        quantity_specs = list({
            item["spec"].expression: item["spec"]
            for item in histogram_data_2d
        }.values())

        canvas_data_2d = create_loaf_2d_canvases(
            histogram_data=histogram_data_2d,
            quantity_specs=quantity_specs,
            show_3d = show_3d,
            show_provenance=show_provenance
        )

    canvases_2d = [
        item.get("canvas")
        for item in canvas_data_2d
    ]

    canvas_names_2d = [
        item.get("canvas_name")
        for item in canvas_data_2d
    ]

    result = {
        "canvas": canvas_1d,
        "canvas_name": canvas_name_1d,
        "legends": legends_1d,
        "drawn_histograms_1d": drawn_histograms_1d,
        "canvas_result_1d": canvas_result_1d,
        "canvases_2d": canvases_2d,
        "canvas_names_2d": canvas_names_2d,
        "canvas_data_2d": canvas_data_2d,
        "histogram_data_1d": histogram_data_1d,
        "histogram_data_2d": histogram_data_2d,
        "histogram_data": [
            *histogram_data_1d,
            *histogram_data_2d,
        ],
    }

    return result

def _validate_and_normalize_histograms(
    histograms: Any,
    quantity: str | None,
    dataframe_label: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    Validate input and convert histograms into canvas metadata.

    Supported inputs:
        histogram

        {
            dataframe_label: histogram,
        }

        {
            quantity: {
                dataframe_label: histogram,
            },
        }
    """
    if not isinstance(dataframe_label, str):
        raise PlotCreationError(
            "dataframe_label must be a string."
        )

    if quantity is not None and not isinstance(quantity, str):
        raise PlotCreationError(
            "quantity must be a string or None."
        )

    # ------------------------------------------------------------
    # Single ROOT histogram
    # ------------------------------------------------------------

    if _is_root_histogram(histograms):
        expression = (
            quantity
            if quantity is not None
            else _infer_histogram_quantity(histograms)
        )

        spec = _get_loaf_quantities(expression)[0]

        _validate_histogram_dimension(
            histogram=histograms,
            spec=spec,
        )

        return _build_histogram_metadata([
            (
                spec,
                dataframe_label,
                histograms,
            )
        ])

    # ------------------------------------------------------------
    # Dictionary input
    # ------------------------------------------------------------

    if not isinstance(histograms, dict):
        raise PlotCreationError(
            "histograms must be a ROOT TH1/TH2 or a dictionary."
        )

    if not histograms:
        raise PlotCreationError(
            "No histograms were supplied."
        )

    first_value = next(iter(histograms.values()))

    # ------------------------------------------------------------
    # dataframe_label -> histogram
    # ------------------------------------------------------------

    if _is_root_histogram(first_value):
        expression = (
            quantity
            if quantity is not None
            else _infer_histogram_quantity(first_value)
        )

        spec = _get_loaf_quantities(expression)[0]

        items: list[
            tuple[LoafQuantitySpec, str, Any]
        ] = []

        for label, histogram in histograms.items():
            if not _is_root_histogram(histogram):
                raise PlotCreationError(
                    "All values must be ROOT TH1/TH2 histograms "
                    "when using the "
                    "'dataframe_label -> histogram' form."
                )

            _validate_histogram_dimension(
                histogram=histogram,
                spec=spec,
            )

            items.append(
                (
                    spec,
                    str(label),
                    histogram,
                )
            )

        return _build_histogram_metadata(items)

    # ------------------------------------------------------------
    # quantity -> {dataframe_label -> histogram}
    # ------------------------------------------------------------

    if isinstance(first_value, dict):
        items: list[
            tuple[LoafQuantitySpec, str, Any]
        ] = []

        for expression, dataset_histograms in histograms.items():
            if not isinstance(dataset_histograms, dict):
                raise PlotCreationError(
                    "All values must be dictionaries when using "
                    "the 'quantity -> {dataframe_label: histogram}' "
                    "form."
                )

            spec = _get_loaf_quantities(
                str(expression)
            )[0]

            for label, histogram in dataset_histograms.items():
                if not _is_root_histogram(histogram):
                    raise PlotCreationError(
                        f"Expected a ROOT TH1/TH2 for "
                        f"quantity {expression!r}, "
                        f"dataframe {label!r}."
                    )

                _validate_histogram_dimension(
                    histogram=histogram,
                    spec=spec,
                )

                items.append(
                    (
                        spec,
                        str(label),
                        histogram,
                    )
                )

        return _build_histogram_metadata(items)

    raise PlotCreationError(
        "Invalid histogram dictionary.\n\n"
        "Expected either:\n"
        "    dataframe_label -> histogram\n\n"
        "or:\n"
        "    quantity -> {dataframe_label -> histogram}"
    )

def _validate_histogram_dimension(
    histogram: Any,
    spec: LoafQuantitySpec,
) -> None:
    """Validate that ROOT histogram and quantity dimensions agree."""
    histogram_is_2d = _is_root_2d_histogram(histogram)

    if histogram_is_2d and spec.dimension != 2:
        raise PlotCreationError(
            f"Histogram {histogram.GetName()!r} is two-dimensional, "
            f"but quantity {spec.expression!r} is one-dimensional."
        )

    if not histogram_is_2d and spec.dimension != 1:
        raise PlotCreationError(
            f"Histogram {histogram.GetName()!r} is one-dimensional, "
            f"but quantity {spec.expression!r} is two-dimensional."
        )

def _build_histogram_metadata(
    items: list[
        tuple[LoafQuantitySpec, str, Any]
    ],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Build metadata required by the Loaf canvas helpers."""
    histogram_data_1d: list[dict[str, Any]] = []
    histogram_data_2d: list[dict[str, Any]] = []

    dataset_indices: dict[str, int] = {}

    for spec, label, histogram in items:
        dataset_index = dataset_indices.get(label)

        if dataset_index is None:
            dataset_index = len(dataset_indices) + 1
            dataset_indices[label] = dataset_index

        if spec.dimension == 2:
            histogram_data_2d.append(
                _build_2d_histogram_metadata(
                    histogram=histogram,
                    spec=spec,
                    label=label,
                    dataset_index=dataset_index,
                )
            )
        else:
            histogram_data_1d.append(
                _build_1d_histogram_metadata(
                    histogram=histogram,
                    spec=spec,
                    label=label,
                    dataset_index=dataset_index,
                )
            )

    return histogram_data_1d, histogram_data_2d


def _build_1d_histogram_metadata(
    histogram: Any,
    spec: LoafQuantitySpec,
    label: str,
    dataset_index: int,
) -> dict[str, Any]:
    """Create canvas metadata for one TH1 histogram."""
    x_axis = histogram.GetXaxis()

    return {
        "result": None,
        "histogram": histogram,
        "spec": spec,
        "quantity": spec.expression,
        "dimension": 1,
        "dataset_index": dataset_index,
        "dataset_label": label,
        "minimum": float(x_axis.GetXmin()),
        "maximum": float(x_axis.GetXmax()),
        "bins": int(histogram.GetNbinsX()),
        "entries": int(histogram.GetEntries()),
        "normalized": False,
        "lifetime_corrected": False,
        "background_subtracted": False,
    }


def _build_2d_histogram_metadata(
    histogram: Any,
    spec: LoafQuantitySpec,
    label: str,
    dataset_index: int,
) -> dict[str, Any]:
    """Create canvas metadata for one TH2 histogram."""
    x_axis = histogram.GetXaxis()
    y_axis = histogram.GetYaxis()

    return {
        "result": None,
        "histogram": histogram,
        "spec": spec,
        "expression": spec.expression,
        "dimension": 2,
        "dataset_index": dataset_index,
        "dataset_label": label,
        "entries": int(histogram.GetEntries()),
        "normalized": False,
        "x_bins": int(histogram.GetNbinsX()),
        "x_minimum": float(x_axis.GetXmin()),
        "x_maximum": float(x_axis.GetXmax()),
        "y_bins": int(histogram.GetNbinsY()),
        "y_minimum": float(y_axis.GetXmin()),
        "y_maximum": float(y_axis.GetXmax()),
    }

def _is_root_histogram(value: Any) -> bool:
    """Return True for ROOT TH1-derived objects, including TH2."""
    return bool(
        value is not None
        and hasattr(value, "InheritsFrom")
        and value.InheritsFrom("TH1")
    )


def _is_root_2d_histogram(histogram: Any) -> bool:
    """Return True for ROOT TH2-derived histograms."""
    return bool(
        histogram.InheritsFrom("TH2")
    )


def _infer_histogram_quantity(
    histogram: Any,
) -> str:
    """
    Infer the quantity name from a ROOT histogram.

    Explicitly supplying ``quantity`` is preferable because ROOT
    axis titles may not contain the original dataframe column names.
    """
    x_axis = histogram.GetXaxis()
    x_quantity = x_axis.GetTitle().strip()

    if _is_root_2d_histogram(histogram):
        y_quantity = (
            histogram
            .GetYaxis()
            .GetTitle()
            .strip()
        )

        if x_quantity and y_quantity:
            return f"{y_quantity}:{x_quantity}"

    elif x_quantity:
        return x_quantity

    return str(histogram.GetName())

def _get_loaf_quantities(
    quantities: str | list[str],
) -> list[LoafQuantitySpec]:
    """Parse one or more Loaf quantities."""
    if isinstance(quantities, str):
        supplied_quantities = [quantities]

    elif isinstance(quantities, list):
        supplied_quantities = quantities

    else:
        raise PlotCreationError(
            "quantities must be a string or list of strings."
        )

    if not supplied_quantities:
        raise PlotCreationError(
            "At least one Loaf quantity must be provided."
        )

    quantity_specs: list[LoafQuantitySpec] = []
    used_expressions: set[str] = set()

    for quantity in supplied_quantities:
        if not isinstance(quantity, str):
            raise PlotCreationError(
                "Every quantity must be a string."
            )

        expression = quantity.strip()

        if not expression:
            raise PlotCreationError(
                "Quantity cannot be empty."
            )

        colon_count = expression.count(":")

        if colon_count == 0:
            spec = LoafQuantitySpec(
                expression=expression,
                dimension=1,
                column=expression,
            )

        elif colon_count == 1:
            y_column, x_column = (
                part.strip()
                for part in expression.split(":", 1)
            )

            if not x_column or not y_column:
                raise PlotCreationError(
                    f"Invalid 2D quantity {expression!r}. "
                    "Use the form 'Y_column:X_column'."
                )

            spec = LoafQuantitySpec(
                expression=expression,
                dimension=2,
                x_column=x_column,
                y_column=y_column,
            )

        else:
            raise PlotCreationError(
                f"Invalid quantity {expression!r}. "
                "Only one ':' is allowed."
            )

        if expression not in used_expressions:
            used_expressions.add(expression)
            quantity_specs.append(spec)

    return quantity_specs