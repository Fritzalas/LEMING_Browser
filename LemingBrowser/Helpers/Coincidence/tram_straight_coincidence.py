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

    Behavior
    --------
    Only branches actually used by active cuts are required
    to be non-empty.

    Output-only branches are allowed to be empty.

    Example:

        Z1L      = [13]
        Z2L      = [13.1]
        Y1L      = []
        time_Z1L = [5000]
        time_Z2L = []

    If the active cuts use only:

        Z1L
        Z2L
        time_Z1L

    and those cuts pass, then:

        StraightZ1L     = [13]
        StraightZ2L     = [13.1]
        StraightY1L     = []
        StraightTimeZ1L = [5000]
        StraightTimeZ2L = []

    Only the first hit of every available branch is used.
    """

    # ---------------------------------------------------------
    # Normalize dataframe input
    # ---------------------------------------------------------

    single_dataframe = not isinstance(
        dataframes,
        (list, tuple),
    )

    dataframe_list = (
        [dataframes]
        if single_dataframe
        else list(dataframes)
    )

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

    unknown_settings = (
        set(settings)
        - supported_settings
    )

    if unknown_settings:
        raise CoincidenceError(
            "Unknown straight-coincidence settings: "
            + ", ".join(
                sorted(unknown_settings)
            )
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
    # Required columns
    #
    # These columns must exist in the dataframe because they
    # may be exposed as Straight... output columns.
    #
    # They do NOT all have to be non-empty for a side to pass.
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
    # Build coincidence conditions
    #
    # Start empty.
    #
    # Each active cut adds:
    #
    #   1. the necessary empty() protection
    #   2. the actual numerical condition
    #
    # This means output-only branches do not influence whether
    # a side passes.
    # ---------------------------------------------------------

    left_conditions: list[str] = []
    right_conditions: list[str] = []

    def add_optional_cut(
        conditions: list[str],
        key: str,
        expression: str,
    ) -> None:
        value = values.get(key)

        if value is not None:
            conditions.append(
                expression.format(
                    value=value
                )
            )

    # ---------------------------------------------------------
    # Left cuts
    # ---------------------------------------------------------

    add_optional_cut(
        left_conditions,
        "delta_z_max_left",
        (
            "!Z1L.empty()"
            " && !Z2L.empty()"
            " && std::abs("
            "Z1L[0] - Z2L[0]"
            ") < {value}"
        ),
    )

    add_optional_cut(
        left_conditions,
        "z1_min_left",
        (
            "!Z1L.empty()"
            " && Z1L[0] > {value}"
        ),
    )

    add_optional_cut(
        left_conditions,
        "z1_max_left",
        (
            "!Z1L.empty()"
            " && Z1L[0] < {value}"
        ),
    )

    add_optional_cut(
        left_conditions,
        "z2_min_left",
        (
            "!Z2L.empty()"
            " && Z2L[0] > {value}"
        ),
    )

    add_optional_cut(
        left_conditions,
        "z2_max_left",
        (
            "!Z2L.empty()"
            " && Z2L[0] < {value}"
        ),
    )

    add_optional_cut(
        left_conditions,
        "z1_edep_min_left",
        (
            "!edep_Z1L.empty()"
            " && edep_Z1L[0] > {value}"
        ),
    )

    add_optional_cut(
        left_conditions,
        "z1_edep_max_left",
        (
            "!edep_Z1L.empty()"
            " && edep_Z1L[0] < {value}"
        ),
    )

    add_optional_cut(
        left_conditions,
        "z2_edep_min_left",
        (
            "!edep_Z2L.empty()"
            " && edep_Z2L[0] > {value}"
        ),
    )

    add_optional_cut(
        left_conditions,
        "z2_edep_max_left",
        (
            "!edep_Z2L.empty()"
            " && edep_Z2L[0] < {value}"
        ),
    )

    add_optional_cut(
        left_conditions,
        "z1_time_min_left",
        (
            "!time_Z1L.empty()"
            " && time_Z1L[0] > {value}"
        ),
    )

    add_optional_cut(
        left_conditions,
        "z1_time_max_left",
        (
            "!time_Z1L.empty()"
            " && time_Z1L[0] < {value}"
        ),
    )

    add_optional_cut(
        left_conditions,
        "z2_time_min_left",
        (
            "!time_Z2L.empty()"
            " && time_Z2L[0] > {value}"
        ),
    )

    add_optional_cut(
        left_conditions,
        "z2_time_max_left",
        (
            "!time_Z2L.empty()"
            " && time_Z2L[0] < {value}"
        ),
    )

    # ---------------------------------------------------------
    # Right cuts
    # ---------------------------------------------------------

    add_optional_cut(
        right_conditions,
        "delta_z_max_right",
        (
            "!Z1R.empty()"
            " && !Z2R.empty()"
            " && std::abs("
            "Z1R[0] - Z2R[0]"
            ") < {value}"
        ),
    )

    add_optional_cut(
        right_conditions,
        "z1_min_right",
        (
            "!Z1R.empty()"
            " && Z1R[0] > {value}"
        ),
    )

    add_optional_cut(
        right_conditions,
        "z1_max_right",
        (
            "!Z1R.empty()"
            " && Z1R[0] < {value}"
        ),
    )

    add_optional_cut(
        right_conditions,
        "z2_min_right",
        (
            "!Z2R.empty()"
            " && Z2R[0] > {value}"
        ),
    )

    add_optional_cut(
        right_conditions,
        "z2_max_right",
        (
            "!Z2R.empty()"
            " && Z2R[0] < {value}"
        ),
    )

    add_optional_cut(
        right_conditions,
        "z1_edep_min_right",
        (
            "!edep_Z1R.empty()"
            " && edep_Z1R[0] > {value}"
        ),
    )

    add_optional_cut(
        right_conditions,
        "z1_edep_max_right",
        (
            "!edep_Z1R.empty()"
            " && edep_Z1R[0] < {value}"
        ),
    )

    add_optional_cut(
        right_conditions,
        "z2_edep_min_right",
        (
            "!edep_Z2R.empty()"
            " && edep_Z2R[0] > {value}"
        ),
    )

    add_optional_cut(
        right_conditions,
        "z2_edep_max_right",
        (
            "!edep_Z2R.empty()"
            " && edep_Z2R[0] < {value}"
        ),
    )

    add_optional_cut(
        right_conditions,
        "z1_time_min_right",
        (
            "!time_Z1R.empty()"
            " && time_Z1R[0] > {value}"
        ),
    )

    add_optional_cut(
        right_conditions,
        "z1_time_max_right",
        (
            "!time_Z1R.empty()"
            " && time_Z1R[0] < {value}"
        ),
    )

    add_optional_cut(
        right_conditions,
        "z2_time_min_right",
        (
            "!time_Z2R.empty()"
            " && time_Z2R[0] > {value}"
        ),
    )

    add_optional_cut(
        right_conditions,
        "z2_time_max_right",
        (
            "!time_Z2R.empty()"
            " && time_Z2R[0] < {value}"
        ),
    )

    # ---------------------------------------------------------
    # Final side conditions
    #
    # No active cuts means the side itself is accepted.
    #
    # Individual output columns still check whether their
    # source vector actually contains a value.
    # ---------------------------------------------------------

    left_condition = (
        " && ".join(
            f"({condition})"
            for condition in left_conditions
        )
        if left_conditions
        else "true"
    )

    right_condition = (
        " && ".join(
            f"({condition})"
            for condition in right_conditions
        )
        if right_conditions
        else "true"
    )

    # ---------------------------------------------------------
    # Output helper
    #
    # The overall coincidence condition must pass.
    #
    # Then the individual source column must be non-empty.
    #
    # If the source is empty, this derived output is simply [].
    # ---------------------------------------------------------

    def selected_value(
        condition_column: str,
        source_column: str,
        expression: str,
    ) -> str:
        return (
            "("
            f"{condition_column}"
            " && "
            f"!{source_column}.empty()"
            ")"
            " ? ROOT::VecOps::RVec<double>{"
            f"static_cast<double>({expression})"
            "}"
            " : ROOT::VecOps::RVec<double>{}"
        )

    # ---------------------------------------------------------
    # Output definitions
    # ---------------------------------------------------------

    left_outputs = {
        "StraightZ1L": (
            "Z1L",
            "Z1L[0]",
        ),
        "StraightZ2L": (
            "Z2L",
            "Z2L[0]",
        ),
        "StraightY1L": (
            "Y1L",
            "Y1L[0]",
        ),
        "StraightTimeZ1L": (
            "time_Z1L",
            "time_Z1L[0]",
        ),
        "StraightTimeZ2L": (
            "time_Z2L",
            "time_Z2L[0]",
        ),
        "StraightEdepZ1L": (
            "edep_Z1L",
            "edep_Z1L[0]",
        ),
        "StraightEdepZ2L": (
            "edep_Z2L",
            "edep_Z2L[0]",
        ),
    }

    right_outputs = {
        "StraightZ1R": (
            "Z1R",
            "Z1R[0]",
        ),
        "StraightZ2R": (
            "Z2R",
            "Z2R[0]",
        ),
        "StraightY1R": (
            "Y1R",
            "Y1R[0]",
        ),
        "StraightTimeZ1R": (
            "time_Z1R",
            "time_Z1R[0]",
        ),
        "StraightTimeZ2R": (
            "time_Z2R",
            "time_Z2R[0]",
        ),
        "StraightEdepZ1R": (
            "edep_Z1R",
            "edep_Z1R[0]",
        ),
        "StraightEdepZ2R": (
            "edep_Z2R",
            "edep_Z2R[0]",
        ),
    }

    # ---------------------------------------------------------
    # Build transformed dataframes
    # ---------------------------------------------------------

    result: list[Any] = []

    for dataframe in dataframe_list:
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

        # Left outputs.
        for (
            column_name,
            (
                source_column,
                expression,
            ),
        ) in left_outputs.items():
            dataframe = dataframe.Define(
                column_name,
                selected_value(
                    "__StraightLeftPass",
                    source_column,
                    expression,
                ),
            )

        # Right outputs.
        for (
            column_name,
            (
                source_column,
                expression,
            ),
        ) in right_outputs.items():
            dataframe = dataframe.Define(
                column_name,
                selected_value(
                    "__StraightRightPass",
                    source_column,
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
                "selection_policy": (
                    "Only branches referenced by active cuts "
                    "are required to be non-empty. "
                    "Output-only branches may be empty and "
                    "produce empty derived RVecs."
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
    # Preserve original input shape
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
        required_columns
        - available_columns
    )

    if missing_columns:
        raise CoincidenceError(
            "Required branches are missing from the dataframe: "
            + ", ".join(
                sorted(missing_columns)
            )
        )