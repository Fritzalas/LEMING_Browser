from typing import Any
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from Exceptions.CoincidenceError import CoincidenceError
from Provenance.provenance import register_provenance


def define_tram_straight_coincidence_columns(
    dataframes: Any | list[Any],
    settings: dict[str, float | None] | None,
) -> Any | list[Any]:
    """
    Add straight-coincidence derived columns.

    Accepts either:
        - one dataframe
        - a list of dataframes

    Returns the same form:
        - one dataframe -> one dataframe
        - list -> list

    Every numerical cut is optional.

    If a setting is:
        - a number: apply that cut
        - None: do not apply that cut
        - missing: do not apply that cut

    Only the first hit of every branch is used.

    Provenance is registered once for each resulting dataframe,
    with the original input dataframe as its parent.
    """

    # ---------------------------------------------------------
    # Normalize dataframe input
    # ---------------------------------------------------------

    single_dataframe = not isinstance(dataframes, list)

    if single_dataframe:
        dataframes = [dataframes]

    # ---------------------------------------------------------
    # Normalize and validate settings
    # ---------------------------------------------------------

    settings = settings or {}

    supported_settings = {
        # Delta Z
        "delta_z_max_left",
        "delta_z_max_right",

        # Z1L
        "z1_min_left",
        "z1_max_left",
        "z1_edep_min_left",
        "z1_edep_max_left",
        "z1_time_min_left",
        "z1_time_max_left",

        # Z2L
        "z2_min_left",
        "z2_max_left",
        "z2_edep_min_left",
        "z2_edep_max_left",
        "z2_time_min_left",
        "z2_time_max_left",

        # Z1R
        "z1_min_right",
        "z1_max_right",
        "z1_edep_min_right",
        "z1_edep_max_right",
        "z1_time_min_right",
        "z1_time_max_right",

        # Z2R
        "z2_min_right",
        "z2_max_right",
        "z2_edep_min_right",
        "z2_edep_max_right",
        "z2_time_min_right",
        "z2_time_max_right",
    }

    unknown_settings = set(settings) - supported_settings

    if unknown_settings:
        raise CoincidenceError(
            "Unknown straight-coincidence settings: "
            + ", ".join(sorted(unknown_settings))
        )

    values: dict[str, float | None] = {
        key: (
            None
            if value is None
            else float(value)
        )
        for key, value in settings.items()
    }

    active_settings = {
        key: value
        for key, value in values.items()
        if value is not None
    }

    # ---------------------------------------------------------
    # Required input columns
    # ---------------------------------------------------------

    required_columns = {
        # Left
        "Z1L",
        "Z2L",
        "Y1L",
        "time_Z1L",
        "time_Z2L",
        "edep_Z1L",
        "edep_Z2L",

        # Right
        "Z1R",
        "Z2R",
        "Y1R",
        "time_Z1R",
        "time_Z2R",
        "edep_Z1R",
        "edep_Z2R",
    }

    # ---------------------------------------------------------
    # Base coincidence conditions
    # ---------------------------------------------------------

    left_conditions = [
        "!Z1L.empty()",
        "!Z2L.empty()",
        "!Y1L.empty()",
        "!time_Z1L.empty()",
        "!time_Z2L.empty()",
        "!edep_Z1L.empty()",
        "!edep_Z2L.empty()",
    ]

    right_conditions = [
        "!Z1R.empty()",
        "!Z2R.empty()",
        "!Y1R.empty()",
        "!time_Z1R.empty()",
        "!time_Z2R.empty()",
        "!edep_Z1R.empty()",
        "!edep_Z2R.empty()",
    ]

    def add_optional_cut(
        conditions: list[str],
        key: str,
        expression: str,
    ) -> None:
        value = values.get(key)

        if value is not None:
            conditions.append(
                expression.format(value=value)
            )

    # ---------------------------------------------------------
    # Left cuts
    # ---------------------------------------------------------

    add_optional_cut(
        left_conditions,
        "delta_z_max_left",
        "std::abs(Z1L[0] - Z2L[0]) < {value}",
    )

    add_optional_cut(
        left_conditions,
        "z1_min_left",
        "Z1L[0] > {value}",
    )

    add_optional_cut(
        left_conditions,
        "z1_max_left",
        "Z1L[0] < {value}",
    )

    add_optional_cut(
        left_conditions,
        "z2_min_left",
        "Z2L[0] > {value}",
    )

    add_optional_cut(
        left_conditions,
        "z2_max_left",
        "Z2L[0] < {value}",
    )

    add_optional_cut(
        left_conditions,
        "z1_edep_min_left",
        "edep_Z1L[0] > {value}",
    )

    add_optional_cut(
        left_conditions,
        "z1_edep_max_left",
        "edep_Z1L[0] < {value}",
    )

    add_optional_cut(
        left_conditions,
        "z2_edep_min_left",
        "edep_Z2L[0] > {value}",
    )

    add_optional_cut(
        left_conditions,
        "z2_edep_max_left",
        "edep_Z2L[0] < {value}",
    )

    add_optional_cut(
        left_conditions,
        "z1_time_min_left",
        "time_Z1L[0] > {value}",
    )

    add_optional_cut(
        left_conditions,
        "z1_time_max_left",
        "time_Z1L[0] < {value}",
    )

    add_optional_cut(
        left_conditions,
        "z2_time_min_left",
        "time_Z2L[0] > {value}",
    )

    add_optional_cut(
        left_conditions,
        "z2_time_max_left",
        "time_Z2L[0] < {value}",
    )

    # ---------------------------------------------------------
    # Right cuts
    # ---------------------------------------------------------

    add_optional_cut(
        right_conditions,
        "delta_z_max_right",
        "std::abs(Z1R[0] - Z2R[0]) < {value}",
    )

    add_optional_cut(
        right_conditions,
        "z1_min_right",
        "Z1R[0] > {value}",
    )

    add_optional_cut(
        right_conditions,
        "z1_max_right",
        "Z1R[0] < {value}",
    )

    add_optional_cut(
        right_conditions,
        "z2_min_right",
        "Z2R[0] > {value}",
    )

    add_optional_cut(
        right_conditions,
        "z2_max_right",
        "Z2R[0] < {value}",
    )

    add_optional_cut(
        right_conditions,
        "z1_edep_min_right",
        "edep_Z1R[0] > {value}",
    )

    add_optional_cut(
        right_conditions,
        "z1_edep_max_right",
        "edep_Z1R[0] < {value}",
    )

    add_optional_cut(
        right_conditions,
        "z2_edep_min_right",
        "edep_Z2R[0] > {value}",
    )

    add_optional_cut(
        right_conditions,
        "z2_edep_max_right",
        "edep_Z2R[0] < {value}",
    )

    add_optional_cut(
        right_conditions,
        "z1_time_min_right",
        "time_Z1R[0] > {value}",
    )

    add_optional_cut(
        right_conditions,
        "z1_time_max_right",
        "time_Z1R[0] < {value}",
    )

    add_optional_cut(
        right_conditions,
        "z2_time_min_right",
        "time_Z2R[0] > {value}",
    )

    add_optional_cut(
        right_conditions,
        "z2_time_max_right",
        "time_Z2R[0] < {value}",
    )

    left_condition = " && ".join(
        left_conditions
    )

    right_condition = " && ".join(
        right_conditions
    )

    # ---------------------------------------------------------
    # Output definitions
    # ---------------------------------------------------------

    def selected_value(
        condition_column: str,
        expression: str,
    ) -> str:
        return (
            f"{condition_column}"
            " ? ROOT::VecOps::RVec<double>{"
            f"static_cast<double>({expression})"
            "}"
            " : ROOT::VecOps::RVec<double>{}"
        )

    left_outputs = {
        "StraightZ1L": "Z1L[0]",
        "StraightZ2L": "Z2L[0]",
        "StraightY1L": "Y1L[0]",
        "StraightTimeZ1L": "time_Z1L[0]",
        "StraightTimeZ2L": "time_Z2L[0]",
        "StraightEdepZ1L": "edep_Z1L[0]",
        "StraightEdepZ2L": "edep_Z2L[0]",
    }

    right_outputs = {
        "StraightZ1R": "Z1R[0]",
        "StraightZ2R": "Z2R[0]",
        "StraightY1R": "Y1R[0]",
        "StraightTimeZ1R": "time_Z1R[0]",
        "StraightTimeZ2R": "time_Z2R[0]",
        "StraightEdepZ1R": "edep_Z1R[0]",
        "StraightEdepZ2R": "edep_Z2R[0]",
    }

    # ---------------------------------------------------------
    # Build transformed dataframes
    # ---------------------------------------------------------

    result: list[Any] = []

    for dataframe in dataframes:
        # Keep the original dataframe so provenance points to the
        # dataframe before the straight-coincidence transformation.
        parent_dataframe = dataframe

        _validate_required_columns(
            dataframe,
            required_columns,
        )

        # Define pass/fail conditions.
        dataframe = (
            dataframe
            .Define(
                "__StraightLeftPass",
                left_condition,
            )
            .Define(
                "__StraightRightPass",
                right_condition,
            )
        )

        # Define left-side straight-coincidence columns.
        for column_name, expression in left_outputs.items():
            dataframe = dataframe.Define(
                column_name,
                selected_value(
                    "__StraightLeftPass",
                    expression,
                ),
            )

        # Define right-side straight-coincidence columns.
        for column_name, expression in right_outputs.items():
            dataframe = dataframe.Define(
                column_name,
                selected_value(
                    "__StraightRightPass",
                    expression,
                ),
            )

        # -----------------------------------------------------
        # Register provenance
        # -----------------------------------------------------

        register_provenance(
            dataframe,
            kind="dataframe",
            operation="TRAM straight coincidence",
            parameters={
                "active_settings": active_settings,
                "first_hit_only": True,
                "left_output_columns": list(
                    left_outputs.keys()
                ),
                "right_output_columns": list(
                    right_outputs.keys()
                ),
            },
            parents=[
                parent_dataframe,
            ],
        )

        result.append(
            dataframe
        )

    # ---------------------------------------------------------
    # Preserve input shape
    # ---------------------------------------------------------

    if single_dataframe:
        return result[0]

    return result


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
        raise CoincidenceError(
            "Required branches are missing from the dataframe: "
            + ", ".join(
                sorted(missing_columns)
            )
        )