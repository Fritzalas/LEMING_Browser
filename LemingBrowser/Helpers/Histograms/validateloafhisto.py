from pathlib import Path
from typing import Any
import os
import ROOT
import sys
# getting the name of the directory
# where the this file is present.
current = os.path.dirname(os.path.realpath(__file__))
# Getting the parent directory name
# where the current directory is present.
parent = os.path.dirname(current)
# adding the parent directory to 
# the sys.path.
sys.path.append(parent)
from Exceptions.HistogramError import HistogramError

def validate_create_loaf_histograms_arguments(
    dataframe: Any | list[Any],
    dataframe_labels: list[str],
    quantities: str | list[str],
    bins,
    ranges,
    histogram_config_filename: str | Path,
) -> None:
    _validate_dataframes(
        dataframe=dataframe,
        dataframe_labels=dataframe_labels,
    )

    _validate_quantities(quantities)
    _validate_bins_argument(bins)
    _validate_ranges_argument(ranges)
    _validate_config_filename(histogram_config_filename)

    print("Implicit MT enabled:", ROOT.IsImplicitMTEnabled())
    print("Thread pool size:", ROOT.GetThreadPoolSize())

    print("Histogram input arguments verified.")


def _validate_dataframes(
    dataframe: Any | list[Any],
    dataframe_labels: list[str],
) -> None:
    if dataframe is None:
        raise HistogramError(
            "The dataframe is not available."
        )

    dataframes = (
        dataframe
        if isinstance(dataframe, list)
        else [dataframe]
    )

    if not dataframes:
        raise HistogramError(
            "At least one dataframe must be provided."
        )

    if any(df is None for df in dataframes):
        raise HistogramError(
            "The dataframe list cannot contain None."
        )

    if not isinstance(dataframe_labels, list):
        raise HistogramError(
            "'dataframe_labels' must be a list[str]."
        )

    if len(dataframe_labels) != len(dataframes):
        raise HistogramError(
            "Exactly one dataframe label must be provided "
            "for each dataframe."
        )

    if not dataframe_labels:
        raise HistogramError(
            "'dataframe_labels' cannot be empty."
        )

    cleaned_labels: list[str] = []

    for index, label in enumerate(dataframe_labels):
        if not isinstance(label, str):
            raise HistogramError(
                f"dataframe_labels[{index}] must be a string."
            )

        cleaned_label = label.strip()

        if not cleaned_label:
            raise HistogramError(
                f"dataframe_labels[{index}] cannot be empty."
            )

        cleaned_labels.append(cleaned_label)

    if len(cleaned_labels) != len(set(cleaned_labels)):
        raise HistogramError(
            "'dataframe_labels' must contain unique labels."
        )


def _validate_quantities(
    quantities: str | list[str],
) -> None:
    if isinstance(quantities, str):
        quantities_to_check = [quantities]

    elif isinstance(quantities, list):
        quantities_to_check = quantities

    else:
        raise HistogramError(
            "'quantities' must be a string or list[str]."
        )

    if not quantities_to_check:
        raise HistogramError(
            "'quantities' cannot be empty."
        )

    for index, quantity in enumerate(quantities_to_check):
        if not isinstance(quantity, str):
            raise HistogramError(
                f"quantities[{index}] must be a string."
            )

        if not quantity.strip():
            raise HistogramError(
                f"quantities[{index}] cannot be empty."
            )


def _validate_bins_argument(bins) -> None:
    if bins is None:
        return

    if isinstance(bins, bool):
        raise HistogramError(
            "'bins' cannot be a bool."
        )

    if isinstance(bins, int):
        if bins < 1:
            raise HistogramError(
                "'bins' must be greater than zero."
            )
        return

    if not isinstance(bins, (list, tuple)):
        raise HistogramError(
            "'bins' must be an integer, list, tuple, or None."
        )

    if not bins:
        raise HistogramError(
            "'bins' cannot be an empty collection."
        )


def _validate_ranges_argument(ranges) -> None:
    if ranges is None:
        return

    if not isinstance(ranges, (list, tuple)):
        raise HistogramError(
            "'ranges' must be a list, tuple, or None."
        )

    if not ranges:
        raise HistogramError(
            "'ranges' cannot be empty."
        )


def _validate_config_filename(
    histogram_config_filename: str | Path,
) -> None:
    if not isinstance(
        histogram_config_filename,
        (str, Path),
    ):
        raise HistogramError(
            "'histogram_config_filename' "
            "must be a str or Path."
        )

    if (
        isinstance(histogram_config_filename, str)
        and not histogram_config_filename.strip()
    ):
        raise HistogramError(
            "'histogram_config_filename' cannot be empty."
        )