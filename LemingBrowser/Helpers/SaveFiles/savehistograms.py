######################## Save-histo helper ########################

from pathlib import Path
from typing import Any
import json
import os
import sys
import ROOT
# Get the directory where this file is located.
current = os.path.dirname(
    os.path.realpath(__file__)
)
# Get the parent directory and add it to sys.path.
parent = os.path.dirname(
    current
)
if parent not in sys.path:
    sys.path.append(
        parent
    )

from Exceptions.SaveFileError import SaveFileError
from Provenance.provenance import get_provenance
from Provenance.plot_provenance import create_full_provenance_image
from Classes.ProvenanceNode import ProvenanceNode


def save_histograms(
    output_filename: str | Path | None,
    histogram_data: list[dict] | None,
) -> list[Path]:
    """
    Save histograms and their complete provenance information
    to one ROOT file.

    ROOT-file structure
    -------------------

        output.root

        histogram_1
        histogram_2
        ...

        Provenance/
            histogram_1/
                full_log
                json

            histogram_2/
                full_log
                json

    The provenance is stored twice:

        full_log
            Human-readable complete creation history.

        json
            Complete machine-readable provenance tree.

    No provenance values are abbreviated.
    """

    # ---------------------------------------------------------
    # Validate input
    # ---------------------------------------------------------

    if output_filename is None:
        print(
            "You must enter a filename/path for the "
            "saved ROOT file of histograms."
        )

        return []

    if not histogram_data:
        raise SaveFileError(
            "histogram_data is required when saving a ROOT file."
        )

    output_path = Path(
        output_filename
    ).with_suffix(
        ".root"
    )

    # ---------------------------------------------------------
    # Create output directory
    # ---------------------------------------------------------

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ---------------------------------------------------------
    # Open ROOT file
    # ---------------------------------------------------------

    root_file = ROOT.TFile(
        str(output_path),
        "RECREATE",
    )

    if (
        not root_file
        or root_file.IsZombie()
    ):
        raise SaveFileError(
            f"Could not create ROOT file: {output_path}"
        )

    try:
        # =====================================================
        # Histograms
        # =====================================================

        root_file.cd()

        saved_histograms: list[
            tuple[Any, str]
        ] = []

        used_histogram_names: set[
            str
        ] = set()

        for index, item in enumerate(
            histogram_data,
            start=1,
        ):
            if "histogram" not in item:
                raise SaveFileError(
                    "Each item in histogram_data must contain "
                    "a 'histogram' key."
                )

            histogram = item[
                "histogram"
            ]

            if not isinstance(
                histogram,
                ROOT.TH1,
            ):
                raise SaveFileError(
                    f"Object {histogram!r} is not a ROOT histogram."
                )

            histogram_name = str(
                histogram.GetName()
            ).strip()

            if not histogram_name:
                histogram_name = (
                    f"histogram_{index}"
                )

            histogram_name = (
                _make_unique_name(
                    histogram_name,
                    used_histogram_names,
                )
            )

            used_histogram_names.add(
                histogram_name
            )

            root_file.cd()

            histogram.Write(
                histogram_name
            )

            saved_histograms.append(
                (
                    histogram,
                    histogram_name,
                )
            )

        # =====================================================
        # Provenance directory
        # =====================================================

        root_file.cd()

        provenance_directory = (
            root_file.mkdir(
                "Provenance"
            )
        )

        if provenance_directory is None:
            raise SaveFileError(
                "Could not create Provenance directory "
                "inside the ROOT file."
            )

        # =====================================================
        # Save provenance for every histogram
        # =====================================================

        for (
            histogram,
            histogram_name,
        ) in saved_histograms:

            provenance = get_provenance(
                histogram
            )

            # Histogram created outside provenance-aware code.
            if provenance is None:
                continue

            provenance_directory.cd()

            histogram_provenance_directory = (
                provenance_directory.mkdir(
                    histogram_name
                )
            )

            if histogram_provenance_directory is None:
                raise SaveFileError(
                    "Could not create provenance directory "
                    f"for histogram {histogram_name!r}."
                )

            histogram_provenance_directory.cd()

            # -------------------------------------------------
            # Human-readable full log
            # -------------------------------------------------

            full_log = (
                _create_full_provenance_log(
                    provenance
                )
            )

            full_log_object = ROOT.TObjString(
                full_log
            )

            full_log_object.Write(
                "full_log"
            )

            # -------------------------------------------------
            # Structured JSON
            # -------------------------------------------------

            provenance_dictionary = (
                _provenance_to_dict(
                    provenance
                )
            )

            json_text = json.dumps(
                provenance_dictionary,
                indent=2,
                ensure_ascii=False,
                default=str,
            )

            json_object = ROOT.TObjString(
                json_text
            )

            json_object.Write(
                "json"
            )

            # -------------------------------------------------
            # Full provenance image
            # -------------------------------------------------

            provenance_image_path = (
                create_full_provenance_image(
                    histogram
                )
            )

            provenance_image = ROOT.TImage.Open(
                str(provenance_image_path)
            )

            if provenance_image is None:
                raise SaveFileError(
                    "Could not create provenance image for "
                    f"histogram {histogram_name!r}."
                )

            histogram_provenance_directory.cd()

            provenance_image.Write(
                "provenance_image"
            )

        root_file.Write()

    finally:
        root_file.Close()

    print(
        f"Saved histograms and provenance to {output_path}"
    )

    return [
        output_path
    ]


def _create_full_provenance_log(
    node: ProvenanceNode,
) -> str:
    """
    Produce a complete human-readable provenance log.

    Nothing is abbreviated.

    Shared provenance nodes are printed once and then referenced
    when encountered again.
    """

    lines: list[str] = []

    visited: set[int] = set()

    def walk(
        current_node: ProvenanceNode,
        depth: int,
    ) -> None:
        indent = (
            "    "
            * depth
        )

        # -----------------------------------------------------
        # Shared node already printed
        # -----------------------------------------------------

        if current_node.id in visited:
            lines.append(
                f"{indent}↳ "
                f"[node {current_node.id}] "
                f"{current_node.operation} "
                "(already shown)"
            )

            return

        visited.add(
            current_node.id
        )

        # -----------------------------------------------------
        # Node header
        # -----------------------------------------------------

        lines.append(
            f"{indent}"
            f"[node {current_node.id}] "
            f"{current_node.operation}"
        )

        lines.append(
            f"{indent}"
            f"kind: {current_node.kind}"
        )

        # -----------------------------------------------------
        # Parameters
        # -----------------------------------------------------

        if current_node.parameters:
            lines.append(
                f"{indent}parameters:"
            )

            for key, value in (
                current_node.parameters.items()
            ):
                _append_parameter_log(
                    lines=lines,
                    key=str(key),
                    value=value,
                    depth=depth + 1,
                )

        # -----------------------------------------------------
        # Parents
        # -----------------------------------------------------

        if current_node.parents:
            lines.append(
                f"{indent}parents:"
            )

            for parent_node in current_node.parents:
                walk(
                    parent_node,
                    depth + 1,
                )

    walk(
        node,
        0,
    )

    return "\n".join(
        lines
    )


def _append_parameter_log(
    lines: list[str],
    key: str,
    value: Any,
    depth: int,
) -> None:
    """
    Recursively write one provenance parameter without truncation.
    """

    indent = (
        "    "
        * depth
    )

    # ---------------------------------------------------------
    # Dictionary
    # ---------------------------------------------------------

    if isinstance(
        value,
        dict,
    ):
        lines.append(
            f"{indent}{key}:"
        )

        for child_key, child_value in value.items():
            _append_parameter_log(
                lines=lines,
                key=str(child_key),
                value=child_value,
                depth=depth + 1,
            )

        return

    # ---------------------------------------------------------
    # List / tuple / set
    # ---------------------------------------------------------

    if isinstance(
        value,
        (list, tuple, set),
    ):
        lines.append(
            f"{indent}{key}:"
        )

        for item in value:
            if isinstance(
                item,
                dict,
            ):
                lines.append(
                    f"{indent}    -"
                )

                for child_key, child_value in item.items():
                    _append_parameter_log(
                        lines=lines,
                        key=str(child_key),
                        value=child_value,
                        depth=depth + 2,
                    )

            else:
                lines.append(
                    f"{indent}    - {item}"
                )

        return

    # ---------------------------------------------------------
    # Scalar
    # ---------------------------------------------------------

    lines.append(
        f"{indent}{key}: {value}"
    )


def _provenance_to_dict(
    node: ProvenanceNode,
) -> dict[str, Any]:
    """
    Convert the complete provenance DAG into a JSON-compatible
    structure.

    Shared nodes are stored once in `nodes`, with parent IDs used
    for connections.
    """

    nodes: dict[
        str,
        dict[str, Any],
    ] = {}

    def collect(
        current_node: ProvenanceNode,
    ) -> None:
        node_key = str(
            current_node.id
        )

        if node_key in nodes:
            return

        nodes[node_key] = {
            "id": current_node.id,
            "kind": current_node.kind,
            "operation": current_node.operation,
            "parameters": (
                _make_json_safe(
                    current_node.parameters
                )
            ),
            "parents": [
                parent.id
                for parent in current_node.parents
            ],
        }

        for parent_node in current_node.parents:
            collect(
                parent_node
            )

    collect(
        node
    )

    return {
        "root_node_id": node.id,
        "nodes": nodes,
    }


def _make_json_safe(
    value: Any,
) -> Any:
    """
    Recursively convert provenance metadata into values that
    json.dumps can serialize.
    """

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key): _make_json_safe(
                item
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        (list, tuple, set),
    ):
        return [
            _make_json_safe(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        Path,
    ):
        return str(
            value
        )

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ) or value is None:
        return value

    return str(
        value
    )


def _make_unique_name(
    requested_name: str,
    used_names: set[str],
) -> str:
    """
    Prevent duplicate ROOT object/directory names.
    """

    if requested_name not in used_names:
        return requested_name

    suffix = 2

    while True:
        candidate = (
            f"{requested_name}_{suffix}"
        )

        if candidate not in used_names:
            return candidate

        suffix += 1