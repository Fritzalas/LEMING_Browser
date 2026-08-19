from typing import Any
import os
import sys


# Getting the name of the directory where this file is present.
current = os.path.dirname(
    os.path.realpath(__file__)
)

# Getting the parent directory.
parent = os.path.dirname(current)

# Adding the parent directory to sys.path.
if parent not in sys.path:
    sys.path.append(parent)


from Exceptions.FilterError import FilterError
from Filter.general_apply_filter import global_filter_cut_rdataframe
from Provenance.provenance import register_provenance


def detector_filter_cut_rdataframe(
    dataframes: Any | list[Any],
    detectors: str | list[str],
    cut_filters: str | list[str],
    detector_column: str,
) -> Any | list[Any]:
    """
    ****** Deprecated with the new loaf format ***********
    Apply one cut per detector while leaving all rows from
    other detectors untouched (even at the same event).

    Example:
        detectors = ["Det1", "Det2"]
        cut_filters = ["Energy > 10", "Time < 50"]

    becomes:

        (Idetname != "Det1" || (Energy > 10))
        &&
        (Idetname != "Det2" || (Time < 50))

    Applied identically to every supplied RDataFrame.

    Provenance is registered for each resulting dataframe,
    with the corresponding input dataframe as its parent.
    """

    # ---------------------------------------------------------
    # Preserve dataframe input shape
    # ---------------------------------------------------------

    single_dataframe = not isinstance(
        dataframes,
        list,
    )

    input_dataframes = (
        [dataframes]
        if single_dataframe
        else list(dataframes)
    )

    # ---------------------------------------------------------
    # Normalize detector/cut input
    # ---------------------------------------------------------

    detectors = (
        [detectors]
        if isinstance(detectors, str)
        else list(detectors)
    )

    cut_filters = (
        [cut_filters]
        if isinstance(cut_filters, str)
        else list(cut_filters)
    )

    # ---------------------------------------------------------
    # Validate detector/cut counts
    # ---------------------------------------------------------

    if len(detectors) != len(cut_filters):
        raise FilterError(
            "The number of detectors and cuts must match.\n"
            f"Detectors: {len(detectors)}\n"
            f"Cuts: {len(cut_filters)}"
        )

    # No filters requested.
    if not detectors:
        return dataframes

    # ---------------------------------------------------------
    # Build filter expressions
    # ---------------------------------------------------------

    filters: list[str] = []

    # Keep human-readable settings separately for provenance.
    detector_cuts: list[dict[str, str]] = []

    for index, (detector, cut) in enumerate(
        zip(
            detectors,
            cut_filters,
        ),
        start=1,
    ):
        if not isinstance(detector, str):
            raise FilterError(
                f"Detector {index} must be a string."
            )

        if not isinstance(cut, str):
            raise FilterError(
                f"Cut {index} must be a string."
            )

        detector = detector.strip()
        cut = cut.strip()

        if not detector:
            raise FilterError(
                f"Detector {index} cannot be empty."
            )

        if not cut:
            raise FilterError(
                f"Cut {index} cannot be empty."
            )

        # Keep the original human-readable detector name
        # for provenance before escaping it for C++.
        detector_cuts.append({
            "detector": detector,
            "cut": cut,
        })

        escaped_detector = _escape_cpp_string(
            detector
        )

        filters.append(
            f'({detector_column} != "{escaped_detector}")'
            f' || ({cut})'
        )

    # ---------------------------------------------------------
    # Apply the combined filtering
    # ---------------------------------------------------------

    filtered_dataframes = global_filter_cut_rdataframe(
        dataframes,
        filters,
    )

    # ---------------------------------------------------------
    # Normalize output shape temporarily for provenance
    # ---------------------------------------------------------

    output_dataframes = (
        [filtered_dataframes]
        if single_dataframe
        else list(filtered_dataframes)
    )

    if len(input_dataframes) != len(output_dataframes):
        raise FilterError(
            "Internal error while registering detector-filter "
            "provenance: the number of input and output "
            "dataframes does not match."
        )

    # ---------------------------------------------------------
    # Register provenance
    # ---------------------------------------------------------

    for input_dataframe, output_dataframe in zip(
        input_dataframes,
        output_dataframes,
    ):
        register_provenance(
            output_dataframe,
            kind="dataframe",
            operation="per-detector filter",
            parameters={
                "detector_column": detector_column,
                "detector_cuts": detector_cuts,
            },
            parents=[
                input_dataframe,
            ],
        )

    # ---------------------------------------------------------
    # Preserve original output shape
    # ---------------------------------------------------------

    return filtered_dataframes


def _escape_cpp_string(
    value: str,
) -> str:
    """
    Escape a Python string so it can safely be inserted
    into a C++ string literal.
    """
    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
    )