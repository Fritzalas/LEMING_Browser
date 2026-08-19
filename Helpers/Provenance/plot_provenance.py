from pathlib import Path
from typing import Any
import os
import sys
import tempfile
from PIL import Image
from graphviz import Digraph


# getting the name of the directory
# where this file is present.
current = os.path.dirname(
    os.path.realpath(__file__)
)

# Getting the parent directory name.
parent = os.path.dirname(current)

# adding the parent directory to sys.path.
if parent not in sys.path:
    sys.path.append(parent)


from Provenance.provenance import get_provenance
from Classes.ProvenanceNode import ProvenanceNode


# Keep temporary directories alive while the Python process/kernel
# is running so the external viewer has time to open the file.
_TEMPORARY_GRAPH_DIRECTORIES: list[
    tempfile.TemporaryDirectory
] = []


_HIDDEN_GRAPH_PARAMETERS = {
    "files",
    "backing_root_file",
    "resolved_directory",
}

_CANVAS_OPERATION_KEYS = {
    "file_selection",
    "rdataframe",
    "volume_cuts",

    "global_filter",
    "column_filter",
    "detector_filter",

    "straight_coincidence",
    "old_loaf_coincidence",

    "histogram_1d",
    "histogram_2d",

    "normalized",
    "lifetime",
    "background",

    "musr",

    "add",
    "subtract",
    "multiply",
    "divide",
}

_SUPPORTED_OUTPUT_FORMATS = {
    "png",
    "svg",
    "pdf",
    "jpg",
    "jpeg",
}


def plot_histogram_provenance(
    histograms: Any | list[Any],
    save: bool,
    output_filename: str | Path,
    output_format: str,
    view: bool,
) -> Path | None:
    """
    Draw the complete creation history of one or more histograms.

    If save=True:
        - the rendered file is kept
        - view controls whether it is opened automatically

    If save=False:
        - the rendered file is created in a temporary directory
        - view=True opens it with the system viewer
        - the temporary file is not written into the working directory
    """

    histogram_list = (
        _validate_plot_histogram_provenance_arguments(
            histograms=histograms,
            save=save,
            output_filename=output_filename,
            output_format=output_format,
            view=view,
        )
    )

    graph = Digraph(
        "HistogramProvenance",
        format=output_format,
    )

    graph.attr(
        rankdir="TB",
        splines="ortho",
    )

    visited: set[int] = set()

    def add_node(
        node: ProvenanceNode,
    ) -> None:
        if node.id in visited:
            return

        visited.add(
            node.id
        )

        label = _make_node_label(
            node
        )

        graph.node(
            str(node.id),
            label=label,
            shape=_node_shape(
                node.kind
            ),
        )

        for parent_node in node.parents:
            add_node(
                parent_node
            )

            graph.edge(
                str(parent_node.id),
                str(node.id),
            )

    for histogram in histogram_list:
        provenance = get_provenance(
            histogram
        )

        # Defensive check. Validation already checks this.
        if provenance is None:
            raise ValueError(
                "No provenance information exists for histogram "
                f"{histogram!r}."
            )

        add_node(
            provenance
        )

    output_path = Path(
        output_filename
    )

    # ---------------------------------------------------------
    # Save permanently
    # ---------------------------------------------------------

    if save:
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        rendered = graph.render(
            filename=output_path.stem,
            directory=str(
                output_path.parent
            ),
            cleanup=True,
            view=view,
        )

        return Path(
            rendered
        )

    # ---------------------------------------------------------
    # View only
    #
    # Graphviz's external viewer needs a real file. Therefore
    # render into a temporary directory and keep that directory
    # alive while the Python process/kernel is running.
    # ---------------------------------------------------------

    temporary_directory = tempfile.TemporaryDirectory(
        prefix="histogram_provenance_"
    )

    _TEMPORARY_GRAPH_DIRECTORIES.append(
        temporary_directory
    )

    graph.render(
        filename=output_path.stem,
        directory=temporary_directory.name,
        cleanup=True,
        view=view,
    )

    return None

def create_full_provenance_image(
    histogram: Any,
    target_width: int = 1600,
    target_height: int = 1200,
    scale_factor: int = 3,
) -> Path:
    """
    Render the complete provenance graph for one histogram as a
    high-quality PNG intended for storage inside a ROOT file and
    viewing through TBrowser/RBrowser.

    The full provenance information is preserved.

    Graphviz first renders a supersampled source image. The image is
    then downsampled with Lanczos filtering and centered on a canvas
    having a controlled size and aspect ratio.

    This prevents ROOT's browser from having to aggressively rescale
    an arbitrarily large Graphviz image.
    """

    if target_width < 1:
        raise ValueError(
            "target_width must be at least 1."
        )

    if target_height < 1:
        raise ValueError(
            "target_height must be at least 1."
        )

    if scale_factor < 1:
        raise ValueError(
            "scale_factor must be at least 1."
        )

    provenance = get_provenance(
        histogram
    )

    if provenance is None:
        raise ValueError(
            "No provenance information exists for "
            f"histogram {histogram!r}."
        )

    # ---------------------------------------------------------
    # Graphviz graph
    # ---------------------------------------------------------

    graph = Digraph(
        "HistogramProvenance",
        format="png",
    )

    graph.attr(
        rankdir="TB",
        splines="ortho",

        # Render large first, then downsample.
        dpi=str(
            160 * scale_factor
        ),

        # Compact graph layout.
        nodesep="0.14",
        ranksep="0.20",

        margin="0.02",
        bgcolor="white",
    )

    # ---------------------------------------------------------
    # Typography
    #
    # Keep this deliberately smaller than the embedded canvas
    # provenance because the full logger contains more text.
    # ---------------------------------------------------------

    graph.attr(
        "node",
        fontname="Helvetica",
        fontsize="8",
        margin="0.07,0.04",
        penwidth="0.9",
    )

    graph.attr(
        "edge",
        fontname="Helvetica",
        fontsize="7",
        arrowsize="0.55",
        penwidth="0.8",
    )

    # ---------------------------------------------------------
    # Add complete provenance DAG
    # ---------------------------------------------------------

    visited: set[int] = set()

    def add_node(
        node: ProvenanceNode,
    ) -> None:
        if node.id in visited:
            return

        visited.add(
            node.id
        )

        graph.node(
            str(node.id),
            label=_make_node_label(
                node
            ),
            shape=_node_shape(
                node.kind
            ),
        )

        for parent_node in node.parents:
            add_node(
                parent_node
            )

            graph.edge(
                str(parent_node.id),
                str(node.id),
            )

    add_node(
        provenance
    )

    # ---------------------------------------------------------
    # Temporary directory
    # ---------------------------------------------------------

    temporary_directory = (
        tempfile.TemporaryDirectory(
            prefix="full_histogram_provenance_"
        )
    )

    _TEMPORARY_GRAPH_DIRECTORIES.append(
        temporary_directory
    )

    temporary_path = Path(
        temporary_directory.name
    )

    # ---------------------------------------------------------
    # Supersampled raw Graphviz output
    # ---------------------------------------------------------

    raw_path = Path(
        graph.render(
            filename="provenance_raw",
            directory=str(
                temporary_path
            ),
            format="png",
            cleanup=True,
            view=False,
        )
    )

    final_path = (
        temporary_path
        / "provenance.png"
    )

    # ---------------------------------------------------------
    # High-quality resize for ROOT browser
    # ---------------------------------------------------------

    with Image.open(
        raw_path
    ) as source_image:
        source_image = (
            source_image.convert(
                "RGB"
            )
        )

        source_width = (
            source_image.width
        )

        source_height = (
            source_image.height
        )

        # Leave a small visual border around the provenance graph.
        usable_width = int(
            target_width * 0.96
        )

        usable_height = int(
            target_height * 0.96
        )

        resize_factor = min(
            usable_width
            / source_width,
            usable_height
            / source_height,
        )

        resized_width = max(
            1,
            int(
                round(
                    source_width
                    * resize_factor
                )
            ),
        )

        resized_height = max(
            1,
            int(
                round(
                    source_height
                    * resize_factor
                )
            ),
        )

        resized_image = (
            source_image.resize(
                (
                    resized_width,
                    resized_height,
                ),
                resample=(
                    Image.Resampling.LANCZOS
                ),
            )
        )

        final_image = Image.new(
            "RGB",
            (
                target_width,
                target_height,
            ),
            "white",
        )

        x_offset = (
            target_width
            - resized_width
        ) // 2

        y_offset = (
            target_height
            - resized_height
        ) // 2

        final_image.paste(
            resized_image,
            (
                x_offset,
                y_offset,
            ),
        )

        final_image.save(
            final_path,
            format="PNG",
            optimize=True,
        )

    # ---------------------------------------------------------
    # Raw supersampled file is no longer necessary.
    # ---------------------------------------------------------

    try:
        raw_path.unlink()
    except OSError:
        pass

    return final_path

def create_temporary_provenance_image(
    histograms: Any | list[Any],
    target_width: int,
    target_height: int,
    scale_factor: int = 3,
) -> Path:
    """
    Create a high-quality provenance PNG specifically sized for
    embedding inside a ROOT TPad.

    The graph is first rendered at high resolution and is then
    downsampled with Lanczos filtering to the exact target size.

    This avoids ROOT having to aggressively resize the Graphviz
    image, which significantly improves text quality.
    """

    histogram_list = (
        list(histograms)
        if isinstance(
            histograms,
            (list, tuple),
        )
        else [histograms]
    )

    if not histogram_list:
        raise ValueError(
            "histograms cannot be empty."
        )

    if target_width <= 0:
        raise ValueError(
            "target_width must be positive."
        )

    if target_height <= 0:
        raise ValueError(
            "target_height must be positive."
        )

    if scale_factor < 1:
        raise ValueError(
            "scale_factor must be at least 1."
        )

    # ---------------------------------------------------------
    # Resolve target provenance nodes
    # ---------------------------------------------------------

    target_nodes: list[
        ProvenanceNode
    ] = []

    for histogram in histogram_list:
        provenance = get_provenance(
            histogram
        )

        if provenance is None:
            raise ValueError(
                "No provenance information exists for "
                f"histogram {histogram!r}."
            )

        target_nodes.append(
            provenance
        )

    # ---------------------------------------------------------
    # Build compact Graphviz graph
    # ---------------------------------------------------------

    graph = Digraph(
        "HistogramProvenance",
        format="png",
    )

    graph.attr(
        rankdir="TB",
        splines="ortho",

        # Render a large source image.
        dpi=str(
            180 * scale_factor
        ),

        nodesep="0.16",
        ranksep="0.24",

        margin="0.03",
        bgcolor="white",

        # Avoid Graphviz trying to force its own aspect ratio.
        ratio="compress",
    )

    # ---------------------------------------------------------
    # Better-looking typography
    # ---------------------------------------------------------

    graph.attr(
        "node",
        fontname="Helvetica",
        fontsize="10",
        margin="0.10,0.06",
        penwidth="1.0",
    )

    graph.attr(
        "edge",
        fontname="Helvetica",
        fontsize="9",
        arrowsize="0.60",
        penwidth="0.9",
    )

    added_nodes: set[int] = set()

    resolved_visible_nodes: dict[
        int,
        list[int],
    ] = {}

    def add_compact_node(
        node: ProvenanceNode,
    ) -> list[int]:
        if node.id in resolved_visible_nodes:
            return resolved_visible_nodes[
                node.id
            ]

        visible_parent_ids: list[int] = []

        for parent_node in node.parents:
            visible_parent_ids.extend(
                add_compact_node(
                    parent_node
                )
            )

        visible_parent_ids = list(
            dict.fromkeys(
                visible_parent_ids
            )
        )

        # Hide only operations that are irrelevant to the
        # compact canvas provenance.
        if not _show_node_in_canvas(
            node
        ):
            resolved_visible_nodes[
                node.id
            ] = visible_parent_ids

            return visible_parent_ids

        if node.id not in added_nodes:
            graph.node(
                str(node.id),
                label=_make_canvas_node_label(
                    node
                ),
                shape=_canvas_node_shape(
                    node
                ),
            )

            added_nodes.add(
                node.id
            )

        for parent_id in visible_parent_ids:
            graph.edge(
                str(parent_id),
                str(node.id),
            )

        result = [
            node.id
        ]

        resolved_visible_nodes[
            node.id
        ] = result

        return result

    for target_node in target_nodes:
        add_compact_node(
            target_node
        )

    # ---------------------------------------------------------
    # Temporary directory
    # ---------------------------------------------------------

    temporary_directory = (
        tempfile.TemporaryDirectory(
            prefix="histogram_provenance_canvas_"
        )
    )

    _TEMPORARY_GRAPH_DIRECTORIES.append(
        temporary_directory
    )

    temporary_path = Path(
        temporary_directory.name
    )

    raw_path = Path(
        graph.render(
            filename="provenance_raw",
            directory=str(
                temporary_path
            ),
            format="png",
            cleanup=True,
            view=False,
        )
    )

    final_path = (
        temporary_path
        / "provenance.png"
    )

    # ---------------------------------------------------------
    # High-quality final sizing
    # ---------------------------------------------------------

    with Image.open(
        raw_path
    ) as source_image:
        source_image = (
            source_image
            .convert("RGB")
        )

        source_width, source_height = (
            source_image.size
        )

        # Preserve Graphviz aspect ratio.
        resize_factor = min(
            target_width
            / source_width,
            target_height
            / source_height,
        )

        resized_width = max(
            1,
            int(
                source_width
                * resize_factor
            ),
        )

        resized_height = max(
            1,
            int(
                source_height
                * resize_factor
            ),
        )

        resized_image = (
            source_image.resize(
                (
                    resized_width,
                    resized_height,
                ),
                Image.Resampling.LANCZOS,
            )
        )

        # -----------------------------------------------------
        # Place the graph on an image having exactly the same
        # aspect ratio as the ROOT provenance pad.
        # -----------------------------------------------------

        final_image = Image.new(
            "RGB",
            (
                target_width,
                target_height,
            ),
            "white",
        )

        x_offset = (
            target_width
            - resized_width
        ) // 2

        y_offset = (
            target_height
            - resized_height
        ) // 2

        final_image.paste(
            resized_image,
            (
                x_offset,
                y_offset,
            ),
        )

        final_image.save(
            final_path,
            format="PNG",
            optimize=True,
        )

    return final_path

def _make_node_label(
    node: ProvenanceNode,
) -> str:
    """
    Build labels for the FULL provenance graph.

    Dictionaries are expanded one entry per line so configuration
    objects such as straight-coincidence settings remain readable.
    """

    lines = [
        node.operation,
    ]

    for key, value in node.parameters.items():
        if value is None:
            continue

        if key in _HIDDEN_GRAPH_PARAMETERS:
            continue

        if isinstance(
            value,
            (list, tuple, set, dict),
        ) and not value:
            continue

        # -----------------------------------------------------
        # Dictionaries
        # -----------------------------------------------------

        if isinstance(
            value,
            dict,
        ):
            lines.append(
                f"{key}:"
            )

            for item_key, item_value in value.items():
                lines.append(
                    f"  {item_key}: "
                    f"{_format_value(
                        item_value
                    )}"
                )

            continue

        # -----------------------------------------------------
        # Everything else
        # -----------------------------------------------------

        lines.append(
            f"{key}: "
            f"{_format_value(value)}"
        )

    return "\n".join(
        lines
    )


def _format_value(
    value: Any,
    max_length: int | None = None,
) -> str:
    """
    Format provenance values for the FULL provenance graph.

    Unlike the compact canvas provenance, this function does not
    truncate dictionaries or lists by number of items.

    All stored provenance information is displayed.
    """

    if isinstance(
        value,
        dict,
    ):
        formatted_items = []

        for key, item_value in value.items():
            formatted_items.append(
                f"{key}="
                f"{_format_value(
                    item_value,
                    max_length=max_length,
                )}"
            )

        text = "; ".join(
            formatted_items
        )

    elif isinstance(
        value,
        (list, tuple, set),
    ):
        formatted_items = [
            _format_value(
                item,
                max_length=max_length,
            )
            for item in value
        ]

        text = (
            "["
            + ", ".join(
                formatted_items
            )
            + "]"
        )

    else:
        text = str(
            value
        )

    # Optional safety limit.
    #
    # None means that the full logger displays the complete value.
    if (
        max_length is not None
        and len(text) > max_length
    ):
        text = (
            text[:max_length]
            + "..."
        )

    return text


def _node_shape(
    kind: str,
) -> str:
    shapes = {
        "files": "folder",
        "dataframe": "box",
        "histogram": "box",
    }

    return shapes.get(
        kind,
        "box",
    )

def _show_node_in_canvas(
    node: ProvenanceNode,
) -> bool:
    """
    Return True if this provenance operation is relevant to the
    compact ROOT-canvas provenance view.

    IMPORTANT:
        Every occurrence of a relevant operation is shown.

    Therefore:

        Global filter A
            ↓
        Straight coincidence
            ↓
        Global filter B
            ↓
        Histogram

    remains exactly that sequence.

    We hide irrelevant operation types, not earlier instances of
    relevant operations.
    """

    key = _operation_key(
        node
    )

    return (
        key
        in _CANVAS_OPERATION_KEYS
    )

def _operation_key(
    node: ProvenanceNode,
) -> str:
    """
    Convert provenance operation names into stable display categories.
    """

    operation = (
        node.operation
        .strip()
        .lower()
    )

    # ---------------------------------------------------------
    # Input
    # ---------------------------------------------------------

    if "root file selection" in operation:
        return "file_selection"

    if "rdataframe creation" in operation:
        return "rdataframe"

    if "volume cuts" in operation:
        return "volume_cuts"

    # ---------------------------------------------------------
    # Filters
    # ---------------------------------------------------------

    if (
        "per-detector event-group filter"
        in operation
    ):
        return "detector_filter"

    if "per-detector filter" in operation:
        return "detector_filter"

    if "column filter" in operation:
        return "column_filter"

    if "global filter" in operation:
        return "global_filter"

    # ---------------------------------------------------------
    # Coincidence
    # ---------------------------------------------------------

    if "straight coincidence" in operation:
        return "straight_coincidence"

    if "old loaf coincidence" in operation:
        return "old_loaf_coincidence"

    # ---------------------------------------------------------
    # Histogram creation
    # ---------------------------------------------------------

    if (
        "histogram 1d" in operation
        or "histo1d" in operation
        or "histo 1d" in operation
    ):
        return "histogram_1d"

    if (
        "histogram 2d" in operation
        or "histo2d" in operation
        or "histo 2d" in operation
    ):
        return "histogram_2d"

    # ---------------------------------------------------------
    # Histogram transformations
    # ---------------------------------------------------------

    if "normal" in operation:
        return "normalized"

    if "lifetime" in operation:
        return "lifetime"

    if "background" in operation:
        return "background"

    if "musr" in operation or "muon spin" in operation:
        return "musr"

    # ---------------------------------------------------------
    # Arithmetic
    # ---------------------------------------------------------

    if (
        "addition" in operation
        or operation == "add"
        or "histogram add" in operation
    ):
        return "add"

    if (
        "subtraction" in operation
        or operation == "subtract"
        or "histogram subtract" in operation
    ):
        return "subtract"

    if (
        "multiplication" in operation
        or operation == "multiply"
        or "histogram multiply" in operation
    ):
        return "multiply"

    if (
        "division" in operation
        or operation == "divide"
        or "histogram divide" in operation
    ):
        return "divide"

    return "other"

def _make_canvas_node_label(
    node: ProvenanceNode,
) -> str:
    key = _operation_key(
        node
    )

    parameters = (
        node.parameters
        or {}
    )

    # =========================================================
    # ROOT-file source
    # =========================================================

    if key == "file_selection":
        return _join_canvas_lines(
            "Input runs",
            _parameter_line(
                "runspec",
                parameters.get("runspec"),
            ),
        )

    # =========================================================
    # RDataFrame
    # =========================================================

    if key == "rdataframe":
        return _join_canvas_lines(
            "RDataFrame",
            _parameter_line(
                "tree",
                parameters.get(
                    "tree_name"
                ),
            ),
        )

    # =========================================================
    # Volume cuts
    # =========================================================

    if key == "volume_cuts":
        return _join_canvas_lines(
            "Volume cuts",

            _parameter_line(
                "runs",
                parameters.get(
                    "runspec"
                ),
            ),

            _parameter_line(
                "tree",
                parameters.get(
                    "tree_name"
                ),
            ),

            _range_line(
                "X",
                parameters.get(
                    "x_range"
                ),
            ),

            _range_line(
                "Y",
                parameters.get(
                    "y_range"
                ),
            ),

            _range_line(
                "Z",
                parameters.get(
                    "z_range"
                ),
            ),
        )

    # =========================================================
    # Filters
    # =========================================================

    if key == "global_filter":
        return _join_canvas_lines(
            "Global filter",
            *_format_cut_lines(
                parameters.get(
                    "cuts"
                )
            ),
        )

    if key == "column_filter":
        return _join_canvas_lines(
            "Column filter",
            *_format_cut_lines(
                parameters.get(
                    "cuts"
                )
            ),
        )

    if key == "detector_filter":
        return _join_canvas_lines(
            "Detector filter",
            *_format_detector_cut_lines(
                parameters.get(
                    "detector_cuts"
                )
            ),
        )

    # =========================================================
    # Coincidence
    # =========================================================

    if key == "straight_coincidence":
        return _join_canvas_lines(
            "Straight coincidence",
            *_format_setting_lines(
                parameters.get(
                    "active_settings"
                )
            ),
        )

    if key == "old_loaf_coincidence":
        return _join_canvas_lines(
            "Old LOAF coincidence",
            _parameter_line(
                "detectors",
                parameters.get(
                    "detectors"
                ),
            ),
        )

    # =========================================================
    # Histogram creation
    # =========================================================

    if key == "histogram_1d":
        return _histogram_1d_canvas_label(
            parameters
        )

    if key == "histogram_2d":
        return _histogram_2d_canvas_label(
            parameters
        )

    # =========================================================
    # Corrections
    # =========================================================

    if key == "normalized":
        return "Normalized"

    if key == "lifetime":
        return "Lifetime corrected"

    if key == "background":
        return "Background removed"

    # =========================================================
    # muSR
    # =========================================================

    if key == "musr":
        return (
            "muSR\n"
            "(A - B) / (A + B)"
        )

    # =========================================================
    # Arithmetic
    # =========================================================

    if key == "add":
        return "ADD"

    if key == "subtract":
        return "SUBTRACT"

    if key == "multiply":
        return "MULTIPLY"

    if key == "divide":
        return "DIVIDE"

    return node.operation

def _histogram_1d_canvas_label(
    parameters: dict[str, Any],
) -> str:
    quantity = (
        parameters.get("quantity")
        or parameters.get("expression")
    )

    dataset = parameters.get(
        "dataframe_label"
    )

    bins = parameters.get(
        "bins"
    )

    histogram_range = parameters.get(
        "range"
    )

    return _join_canvas_lines(
        "Histogram 1D",

        _parameter_line(
            "dataset",
            dataset,
        ),

        _parameter_line(
            "quantity",
            quantity,
        ),

        _parameter_line(
            "bins",
            bins,
        ),

        _range_line(
            "range",
            histogram_range,
        ),
    )


def _histogram_2d_canvas_label(
    parameters: dict[str, Any],
) -> str:
    expression = parameters.get(
        "expression"
    )

    dataset = parameters.get(
        "dataframe_label"
    )

    return _join_canvas_lines(
        "Histogram 2D",

        _parameter_line(
            "dataset",
            dataset,
        ),

        _parameter_line(
            "quantity",
            expression,
        ),

        _parameter_line(
            "X bins",
            parameters.get(
                "x_bins"
            ),
        ),

        _range_line(
            "X",
            parameters.get(
                "x_range"
            ),
        ),

        _parameter_line(
            "Y bins",
            parameters.get(
                "y_bins"
            ),
        ),

        _range_line(
            "Y",
            parameters.get(
                "y_range"
            ),
        ),
    )

def _join_canvas_lines(
    *lines: str | None,
) -> str:
    return "\n".join(
        line
        for line in lines
        if line
    )


def _parameter_line(
    name: str,
    value: Any,
) -> str | None:
    if value is None:
        return None

    if isinstance(
        value,
        (list, tuple, set),
    ):
        value = ", ".join(
            str(item)
            for item in value
        )

    return (
        f"{name}: {value}"
    )


def _range_line(
    name: str,
    value: Any,
) -> str | None:
    if value is None:
        return None

    if (
        isinstance(
            value,
            (list, tuple),
        )
        and len(value) == 2
    ):
        return (
            f"{name}: "
            f"{value[0]} to {value[1]}"
        )

    return (
        f"{name}: {value}"
    )


def _format_cut_lines(
    cuts: Any,
) -> list[str]:
    if not cuts:
        return []

    if isinstance(
        cuts,
        str,
    ):
        cuts = [
            cuts
        ]

    return [
        str(cut)
        for cut in cuts
    ]


def _format_detector_cut_lines(
    detector_cuts: Any,
) -> list[str]:
    if not detector_cuts:
        return []

    lines = []

    for item in detector_cuts:
        if not isinstance(
            item,
            dict,
        ):
            continue

        detector = item.get(
            "detector"
        )

        cut = item.get(
            "cut"
        )

        if detector is None:
            continue

        if cut is None:
            lines.append(
                str(detector)
            )

        else:
            lines.append(
                f"{detector}: {cut}"
            )

    return lines


def _format_setting_lines(
    settings: Any,
) -> list[str]:
    if not settings:
        return []

    if not isinstance(
        settings,
        dict,
    ):
        return [
            str(settings)
        ]

    return [
        f"{key}: {value}"
        for key, value
        in settings.items()
    ]

def _canvas_node_shape(
    node: ProvenanceNode,
) -> str:
    key = _operation_key(
        node
    )

    if key in {
        "add",
        "subtract",
        "multiply",
        "divide",
        "musr",
    }:
        return "diamond"

    if key in {
        "normalized",
        "lifetime",
        "background",
    }:
        return "ellipse"

    if key == "file_selection":
        return "folder"

    return "box"

def _validate_plot_histogram_provenance_arguments(
    histograms: Any | list[Any],
    save: bool,
    output_filename: str | Path,
    output_format: str,
    view: bool,
) -> list[Any]:
    """
    Validate all arguments before any Graphviz work is performed.

    Returns the histogram input normalized to a list.
    """

    # ---------------------------------------------------------
    # Histograms
    # ---------------------------------------------------------

    if histograms is None:
        raise ValueError(
            "histograms cannot be None."
        )

    histogram_list = (
        list(histograms)
        if isinstance(histograms, list)
        else [histograms]
    )

    if not histogram_list:
        raise ValueError(
            "histograms cannot be an empty list."
        )

    for index, histogram in enumerate(
        histogram_list,
        start=1,
    ):
        if histogram is None:
            raise ValueError(
                f"Histogram {index} is None."
            )

        if get_provenance(histogram) is None:
            raise ValueError(
                "No provenance information exists for "
                f"histogram {index}: {histogram!r}. "
                "It may have been created outside the "
                "provenance-aware helper functions."
            )

    # ---------------------------------------------------------
    # save
    # ---------------------------------------------------------

    if not isinstance(save, bool):
        raise TypeError(
            "save must be a bool."
        )

    # ---------------------------------------------------------
    # view
    # ---------------------------------------------------------

    if not isinstance(view, bool):
        raise TypeError(
            "view must be a bool."
        )

    if not save and not view:
        raise ValueError(
            "Nothing would be produced because both "
            "save=False and view=False."
        )

    # ---------------------------------------------------------
    # output filename
    # ---------------------------------------------------------

    if not isinstance(
        output_filename,
        (str, Path),
    ):
        raise TypeError(
            "output_filename must be a string or Path."
        )

    if not str(
        output_filename
    ).strip():
        raise ValueError(
            "output_filename cannot be empty."
        )

    # ---------------------------------------------------------
    # output format
    # ---------------------------------------------------------

    if not isinstance(
        output_format,
        str,
    ):
        raise TypeError(
            "output_format must be a string."
        )

    normalized_format = (
        output_format
        .strip()
        .lower()
        .removeprefix(".")
    )

    if normalized_format not in _SUPPORTED_OUTPUT_FORMATS:
        raise ValueError(
            f"Unsupported output format "
            f"{output_format!r}. "
            "Supported formats are: "
            + ", ".join(
                sorted(
                    _SUPPORTED_OUTPUT_FORMATS
                )
            )
        )

    return histogram_list