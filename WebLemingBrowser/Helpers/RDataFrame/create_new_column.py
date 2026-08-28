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

def create_rdataframe_new_column(
    dataframes: Any | list[Any],
    definitions: dict[str, str],
):
    applied_rdataframes = define_columns(
        dataframes=dataframes,
        definitions=definitions
    )
    return applied_rdataframes

def define_columns(
    dataframes: Any | list[Any],
    definitions: dict[str, str],
):
    """
    Add one or more defined columns to one RDataFrame
    or a list of RDataFrames.

    Provenance is registered for each resulting dataframe.

    Example
    -------
    definitions = {
        "RN3_RF3_coinc_time": "(RN3Time + RF3Time) / 2",
        "RN4_RF4_coinc_time": "(RN4Time + RF4Time) / 2",
    }
    """

    # ---------------------------------------------------------
    # Preserve input shape
    # ---------------------------------------------------------

    is_single_dataframe = not isinstance(
        dataframes,
        (list, tuple),
    )

    input_dataframes = (
        [dataframes]
        if is_single_dataframe
        else list(dataframes)
    )

    # ---------------------------------------------------------
    # Apply definitions
    # ---------------------------------------------------------

    result = []

    for input_dataframe in input_dataframes:

        # Keep the original dataframe as the provenance parent.
        dataframe = input_dataframe

        for column_name, expression in definitions.items():
            dataframe = dataframe.Define(
                column_name,
                expression,
            )

    # ---------------------------------------------------------
    # Preserve original input shape
    # ---------------------------------------------------------

    if is_single_dataframe:
        return result[0]

    return result