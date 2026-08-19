from pathlib import Path
from typing import Optional
import os
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

from Exceptions.DataFrameError import DataFrameError


def _get_available_threads() -> int:
    """
    Return the number of CPU threads actually available
    to the current process.

    On Linux, sched_getaffinity respects restrictions from
    SLURM, containers, taskset, CPU pinning, etc.

    Falls back to os.cpu_count() if affinity information
    is unavailable.
    """
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def validate_create_rdataframe_arguments(
    selected_files: list[Path],
    tree_name: str,
    number_of_threads: Optional[int],
    required_columns: Optional[set[str]],
    add_run_subrun_columns: bool,
    debug_preview_dataframe: bool,
) -> None:
    # ---------------------------------------------------------
    # selected_files
    # ---------------------------------------------------------
    if not isinstance(selected_files, list):
        raise DataFrameError(
            "'selected_files' must be a list of Path objects."
        )

    if not selected_files:
        raise DataFrameError(
            "'selected_files' cannot be empty."
        )

    for index, path in enumerate(selected_files):
        if not isinstance(path, Path):
            raise DataFrameError(
                f"selected_files[{index}] must be a Path, "
                f"got {type(path).__name__}."
            )

        if not path.is_file():
            raise DataFrameError(
                f"ROOT file does not exist:\n{path}"
            )

        if path.suffix.lower() != ".root":
            raise DataFrameError(
                f"File is not a ROOT file:\n{path}"
            )

    # ---------------------------------------------------------
    # tree_name
    # ---------------------------------------------------------
    if not isinstance(tree_name, str):
        raise DataFrameError(
            "'tree_name' must be a string."
        )

    if not tree_name.strip():
        raise DataFrameError(
            "'tree_name' cannot be empty."
        )

    # ---------------------------------------------------------
    # number_of_threads
    # ---------------------------------------------------------
    if number_of_threads is not None:
        # bool is a subclass of int, so explicitly reject it.
        if isinstance(number_of_threads, bool):
            raise DataFrameError(
                "'number_of_threads' must be an int or None."
            )

        if not isinstance(number_of_threads, int):
            raise DataFrameError(
                "'number_of_threads' must be an int or None."
            )

        if number_of_threads < 1:
            raise DataFrameError(
                "'number_of_threads' must be at least 1."
            )

        available_threads = _get_available_threads()

        if number_of_threads > available_threads:
            raise DataFrameError(
                "'number_of_threads' cannot be greater than "
                "the number of CPU threads available to this process.\n"
                f"Requested threads: {number_of_threads}\n"
                f"Available threads: {available_threads}"
            )

    # ---------------------------------------------------------
    # required_columns
    # ---------------------------------------------------------
    if required_columns is not None:
        if not isinstance(required_columns, set):
            raise DataFrameError(
                "'required_columns' must be a set[str] or None."
            )

        for column_name in required_columns:
            if not isinstance(column_name, str):
                raise DataFrameError(
                    "Every element of 'required_columns' "
                    "must be a string."
                )

            if not column_name.strip():
                raise DataFrameError(
                    "'required_columns' cannot contain "
                    "empty column names."
                )

    # ---------------------------------------------------------
    # add_run_subrun_columns
    # ---------------------------------------------------------
    if not isinstance(add_run_subrun_columns, bool):
        raise DataFrameError(
            "'add_run_subrun_columns' must be a bool."
        )

    # ---------------------------------------------------------
    # debug_preview_dataframe
    # ---------------------------------------------------------
    if not isinstance(debug_preview_dataframe, bool):
        raise DataFrameError(
            "'debug_preview_dataframe' must be a bool."
        )

    # ---------------------------------------------------------
    # Logical dependency
    # ---------------------------------------------------------
    if debug_preview_dataframe and not add_run_subrun_columns:
        print(
            "WARNING: 'debug_preview_dataframe=True' was requested "
            "while 'add_run_subrun_columns=False'. "
            "The run/subrun preview may not be available unless "
            "those columns already exist."
        )

    print("Input RDataFrame arguments verified.")