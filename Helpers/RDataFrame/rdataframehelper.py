from pathlib import Path
import ROOT
from typing import Optional
from .rdataframe_creation_validation import (
    validate_create_rdataframe_arguments
)
import os
import sys

# getting the name of the directory
# where this file is present.
current = os.path.dirname(
    os.path.realpath(__file__)
)

# Getting the parent directory name
# where the current directory is present.
parent = os.path.dirname(current)

# adding the parent directory to sys.path.
if parent not in sys.path:
    sys.path.append(parent)

from Exceptions.DataFrameError import DataFrameError
from CPP.load_run_subrun_cpp_helper import (
    load_run_subrun_cpp_helpers
)
from Provenance.provenance import register_provenance


def create_rdataframe(
    selected_files: list[Path],
    tree_name: str,
    number_of_threads: Optional[int],
    required_columns: Optional[set[str]],
    add_run_subrun_columns: bool,
    debug_preview_dataframe: bool,
):
    """
    Create a ROOT RDataFrame from the selected ROOT files.

    Provenance is registered for the final dataframe. The selected
    file collection is used as the parent so the dataframe history
    can be traced back to the original run/file selection.
    """

    # ---------------------------------------------------------
    # Validate arguments
    # ---------------------------------------------------------

    validate_create_rdataframe_arguments(
        selected_files=selected_files,
        tree_name=tree_name,
        number_of_threads=number_of_threads,
        required_columns=required_columns,
        add_run_subrun_columns=add_run_subrun_columns,
        debug_preview_dataframe=debug_preview_dataframe,
    )

    # ---------------------------------------------------------
    # Configure ROOT multithreading
    # ---------------------------------------------------------

    _configure_root_multithreading(
        number_of_threads
    )

    # ---------------------------------------------------------
    # Prepare ROOT file vector
    # ---------------------------------------------------------

    root_files = _create_root_file_vector(
        selected_files
    )

    # ---------------------------------------------------------
    # Create dataframe
    # ---------------------------------------------------------

    print("Creating RDataFrame...")

    dataframe = ROOT.RDataFrame(
        tree_name,
        root_files,
    )

    # ---------------------------------------------------------
    # Validate required columns
    # ---------------------------------------------------------

    if required_columns:
        print(
            "Now we validate if the user specified "
            "columns exist in the RDataFrame"
        )

        _validate_required_columns(
            dataframe,
            required_columns,
        )

    # ---------------------------------------------------------
    # Optionally add run/subrun columns
    # ---------------------------------------------------------

    added_run_subrun_columns = []

    if add_run_subrun_columns:
        load_run_subrun_cpp_helpers()

        columns_before = _get_column_names(
            dataframe
        )

        dataframe = _add_run_subrun_columns(
            dataframe
        )

        columns_after = _get_column_names(
            dataframe
        )

        for column_name in (
            "Runnumber",
            "Subrunnumber",
        ):
            if (
                column_name not in columns_before
                and column_name in columns_after
            ):
                added_run_subrun_columns.append(
                    column_name
                )

        if debug_preview_dataframe:
            _log_run_subrun_rows(
                dataframe=dataframe,
                number_of_rows=10,
            )

    # ---------------------------------------------------------
    # Print selected column types
    # ---------------------------------------------------------

    columns_to_print = set(
        required_columns or ()
    )

    available_columns = _get_column_names(
        dataframe
    )

    for column_name in (
        "Runnumber",
        "Subrunnumber",
    ):
        if column_name in available_columns:
            columns_to_print.add(
                column_name
            )

    _print_column_types(
        dataframe,
        columns_to_print,
    )

    print(
        f"Loaded {len(selected_files)} ROOT file(s)."
    )

    print(
        f"Tree: {tree_name}"
    )

    # ---------------------------------------------------------
    # Register provenance
    # ---------------------------------------------------------

    register_provenance(
        dataframe,
        kind="dataframe",
        operation="ROOT RDataFrame creation",
        parameters={
            "tree_name": tree_name,
            "number_of_files": len(
                selected_files
            ),
            "number_of_threads": (
                number_of_threads
            ),
            "implicit_multithreading": (
                number_of_threads is not None
            ),
            "required_columns": sorted(
                required_columns or []
            ),
            "add_run_subrun_columns": (
                add_run_subrun_columns
            ),
            "added_run_subrun_columns": (
                added_run_subrun_columns
            ),
        },
        parents=[
            selected_files,
        ],
    )

    return dataframe


def _configure_root_multithreading(
    number_of_threads: Optional[int],
) -> None:
    if ROOT.IsImplicitMTEnabled():
        ROOT.DisableImplicitMT()

    # None means: do not use ROOT implicit multithreading.
    if number_of_threads is None:
        print(
            "\nROOT implicit multithreading: disabled"
        )
        return

    ROOT.EnableImplicitMT(
        number_of_threads
    )

    print(
        "\nROOT implicit multithreading: enabled"
    )

    print(
        f"ROOT threads: {ROOT.GetThreadPoolSize()}"
    )


def _create_root_file_vector(
    selected_files: list[Path],
):
    root_files = ROOT.std.vector(
        "string"
    )()

    for path in selected_files:
        root_files.push_back(
            str(path)
        )

    return root_files


def _validate_required_columns(
    dataframe,
    required_columns: set[str],
) -> None:
    available_columns = {
        str(column)
        for column in dataframe.GetColumnNames()
    }

    missing_columns = (
        required_columns - available_columns
    )

    if missing_columns:
        raise DataFrameError(
            "Required branches are missing from the dataframe: "
            + ", ".join(
                sorted(missing_columns)
            )
        )


def _add_run_subrun_columns(
    dataframe,
):
    """
    Add Runnumber and Subrunnumber from the current input filename.

    Existing columns are preserved.
    """

    available_columns = {
        str(column_name)
        for column_name in dataframe.GetColumnNames()
    }

    if "Runnumber" in available_columns:
        print(
            "Column 'Runnumber' already exists; "
            "keeping the existing column."
        )
    else:
        dataframe = dataframe.DefinePerSample(
            "Runnumber",
            (
                "ExtractRunNumberFromSample("
                "rdfsampleinfo_.AsString())"
            ),
        )

        print(
            "Added column: Runnumber"
        )

    if "Subrunnumber" in available_columns:
        print(
            "Column 'Subrunnumber' already exists; "
            "keeping the existing column."
        )
    else:
        dataframe = dataframe.DefinePerSample(
            "Subrunnumber",
            (
                "ExtractSubrunNumberFromSample("
                "rdfsampleinfo_.AsString())"
            ),
        )

        print(
            "Added column: Subrunnumber"
        )

    return dataframe


def _print_column_types(
    dataframe,
    column_names: set[str],
) -> None:
    for column_name in sorted(
        column_names
    ):
        print(
            f"{column_name} type: "
            f"{dataframe.GetColumnType(column_name)}"
        )


def _get_column_names(
    dataframe,
) -> set[str]:
    return {
        str(column_name)
        for column_name in dataframe.GetColumnNames()
    }


def _log_run_subrun_rows(
    dataframe,
    number_of_rows: int = 10,
) -> None:
    """
    Print the first and last rows of the dataframe, showing the
    dataframe entry, run number, and subrun number.

    Note: determining the last rows requires evaluating Count().
    """

    if number_of_rows < 1:
        raise DataFrameError(
            "number_of_rows must be at least 1."
        )

    available_columns = _get_column_names(
        dataframe
    )

    required_columns = {
        "Runnumber",
        "Subrunnumber",
    }

    missing_columns = (
        required_columns - available_columns
    )

    if missing_columns:
        print(
            "Cannot preview run/subrun values because these "
            "columns are missing: "
            + ", ".join(
                sorted(missing_columns)
            )
        )
        return

    total_entries = int(
        dataframe.Count().GetValue()
    )

    print(
        f"\nTotal dataframe entries: "
        f"{total_entries}"
    )

    if total_entries == 0:
        print(
            "The dataframe is empty."
        )
        return

    preview_columns = [
        "rdfentry_",
        "Runnumber",
        "Subrunnumber",
    ]

    first_rows = (
        dataframe
        .Filter(
            f"rdfentry_ < {number_of_rows}",
            "first dataframe rows",
        )
        .AsNumpy(
            preview_columns
        )
    )

    last_start = max(
        total_entries - number_of_rows,
        0,
    )

    last_rows = (
        dataframe
        .Filter(
            f"rdfentry_ >= {last_start}",
            "last dataframe rows",
        )
        .AsNumpy(
            preview_columns
        )
    )

    actual_first_count = min(
        number_of_rows,
        total_entries,
    )

    actual_last_count = min(
        number_of_rows,
        total_entries,
    )

    _print_dataframe_rows(
        title=(
            f"First {actual_first_count} "
            "dataframe row(s)"
        ),
        rows=first_rows,
        column_names=preview_columns,
    )

    _print_dataframe_rows(
        title=(
            f"Last {actual_last_count} "
            "dataframe row(s)"
        ),
        rows=last_rows,
        column_names=preview_columns,
    )


def _print_dataframe_rows(
    title: str,
    rows: dict,
    column_names: list[str],
) -> None:
    print(
        "\n" + title
    )

    print(
        "-" * 72
    )

    if not rows:
        print(
            "No rows."
        )
        return

    number_of_rows = len(
        rows[column_names[0]]
    )

    if number_of_rows == 0:
        print(
            "No rows."
        )
        return

    header = " | ".join(
        f"{column_name:>16}"
        for column_name in column_names
    )

    print(
        header
    )

    print(
        "-" * len(header)
    )

    for row_index in range(
        number_of_rows
    ):
        values = []

        for column_name in column_names:
            value = rows[
                column_name
            ][row_index]

            # Convert NumPy/ROOT scalar types into ordinary
            # Python values for cleaner formatting.
            if hasattr(
                value,
                "item",
            ):
                value = value.item()

            values.append(
                f"{value!s:>16}"
            )

        print(
            " | ".join(values)
        )