"""Standalone unit tests for define_tram_straight_coincidence_columns.

Run from the project root:

    python test_define_tram_straight_coincidence_columns_standalone.py

The tests use fresh ROOT.RDataFrame objects and require no external test
framework.

The function under test is expected to support these optional settings:

    delta_z_max_left
    delta_z_max_right

    z1_min_left
    z1_max_left
    z2_min_left
    z2_max_left

    z1_min_right
    z1_max_right
    z2_min_right
    z2_max_right

    z1_edep_min_left
    z1_edep_max_left
    z2_edep_min_left
    z2_edep_max_left

    z1_edep_min_right
    z1_edep_max_right
    z2_edep_min_right
    z2_edep_max_right

    z1_time_min_left
    z1_time_max_left
    z2_time_min_left
    z2_time_max_left

    z1_time_min_right
    z1_time_max_right
    z2_time_min_right
    z2_time_max_right

A missing setting or a setting whose value is None must not add a numerical
comparison. The helper uses the first hit when a source vector is non-empty.
Only branches referenced by active cuts are required to be non-empty; output-only
branches may be empty and then their corresponding Straight... output is empty.
"""

from __future__ import annotations
import itertools
import math
import os
import sys
from typing import Any

import ROOT
ROOT.gInterpreter.Declare(
    """
    #include <cstddef>
    #include <vector>
    #include <ROOT/RVec.hxx>
    """
)

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from Helpers.Coincidence.tram_straight_coincidence import (
    define_tram_straight_coincidence_columns,
)

# ---------------------------------------------------------------------------
# Input and output column definitions
# ---------------------------------------------------------------------------

INPUT_COLUMNS = [
    "Z1L",
    "Z2L",
    "Y1L",
    "time_Z1L",
    "time_Z2L",
    "edep_Z1L",
    "edep_Z2L",
    "Z1R",
    "Z2R",
    "Y1R",
    "time_Z1R",
    "time_Z2R",
    "edep_Z1R",
    "edep_Z2R",
]

OUTPUT_COLUMNS = [
    "StraightZ1L",
    "StraightZ2L",
    "StraightY1L",
    "StraightTimeZ1L",
    "StraightTimeZ2L",
    "StraightEdepZ1L",
    "StraightEdepZ2L",
    "StraightZ1R",
    "StraightZ2R",
    "StraightY1R",
    "StraightTimeZ1R",
    "StraightTimeZ2R",
    "StraightEdepZ1R",
    "StraightEdepZ2R",
]

LEFT_OUTPUT_COLUMNS = OUTPUT_COLUMNS[:7]
RIGHT_OUTPUT_COLUMNS = OUTPUT_COLUMNS[7:]
_TEST_COLUMN_COUNTER = itertools.count()

# ---------------------------------------------------------------------------
# Test-data construction and materialization
# ---------------------------------------------------------------------------

def _declare_test_column(
    values: list[list[Any]],
) -> str:
    """
    Store one complete test column in a C++ global vector.

    Returns the fully qualified C++ variable name. This avoids both:
        - deeply nested ternary expressions
        - switch-lambda return-type inference problems in Cling
    """
    cpp_type = _infer_vector_cpp_type(
        values
    )

    variable_name = (
        "tram_test_column_"
        f"{next(_TEST_COLUMN_COUNTER)}"
    )

    vector_literals = ", ".join(
        _cpp_vector(
            list(value),
            cpp_type,
        )
        for value in values
    )

    declaration = (
        "namespace TramStraightTestData {"
        f" static const std::vector<"
        f"ROOT::VecOps::RVec<{cpp_type}>>"
        f" {variable_name} = {{"
        f"{vector_literals}"
        "};"
        "}"
    )

    success = ROOT.gInterpreter.Declare(
        declaration
    )

    if not success:
        raise RuntimeError(
            "Failed to declare C++ test column "
            f"{variable_name}"
        )

    return (
        "TramStraightTestData::"
        f"{variable_name}"
    )

def _cpp_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float):
        if math.isnan(value):
            return "std::numeric_limits<double>::quiet_NaN()"

        if math.isinf(value):
            if value > 0:
                return "std::numeric_limits<double>::infinity()"
            return "-std::numeric_limits<double>::infinity()"

        return repr(value)

    raise TypeError(
        f"Unsupported scalar test value: {value!r}"
    )


def _infer_vector_cpp_type(
    rows: list[list[Any]],
) -> str:
    flattened = [
        item
        for row in rows
        for item in row
    ]

    if any(
        isinstance(item, float)
        for item in flattened
    ):
        return "double"

    if any(
        isinstance(item, bool)
        for item in flattened
    ):
        return "bool"

    return "int"


def _cpp_vector(
    values: list[Any],
    cpp_type: str,
) -> str:
    body = ", ".join(
        _cpp_scalar(value)
        for value in values
    )

    return (
        f"ROOT::VecOps::RVec<{cpp_type}>"
        f"{{{body}}}"
    )

def make_dataframe(
    rows: list[dict[str, list[float]]],
):
    """
    Create a fresh RDataFrame whose rows match ``rows``.

    Test values are stored in global C++ vectors, and each dataframe
    column reads its value using rdfentry_.
    """
    assert rows, (
        "Tests must contain at least one row."
    )

    columns = list(rows[0])

    assert columns == INPUT_COLUMNS, (
        "Test rows must contain INPUT_COLUMNS "
        "in the declared order."
    )

    assert all(
        list(row) == columns
        for row in rows
    ), (
        "All rows must contain identical columns "
        "in identical order."
    )

    dataframe = ROOT.RDataFrame(
        len(rows)
    )

    for column in columns:
        cpp_storage = _declare_test_column(
            [
                row[column]
                for row in rows
            ]
        )

        dataframe = dataframe.Define(
            column,
            (
                f"{cpp_storage}"
                "[static_cast<std::size_t>("
                "rdfentry_"
                ")]"
            ),
        )

    return dataframe

def _python_value(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()

    if hasattr(value, "item"):
        return value.item()

    try:
        return [
            _python_value(item)
            for item in value
        ]
    except TypeError:
        return value


def materialize(
    dataframe,
    columns: list[str],
) -> list[dict[str, Any]]:
    arrays = dataframe.AsNumpy(columns)

    if not columns:
        return []

    row_count = len(
        arrays[columns[0]]
    )

    return [
        {
            column: _python_value(
                arrays[column][row_index]
            )
            for column in columns
        }
        for row_index in range(row_count)
    ]


# ---------------------------------------------------------------------------
# Row and expected-result helpers
# ---------------------------------------------------------------------------

def event(
    *,
    z1l: list[float] | None = None,
    z2l: list[float] | None = None,
    y1l: list[float] | None = None,
    time_z1l: list[float] | None = None,
    time_z2l: list[float] | None = None,
    edep_z1l: list[float] | None = None,
    edep_z2l: list[float] | None = None,
    z1r: list[float] | None = None,
    z2r: list[float] | None = None,
    y1r: list[float] | None = None,
    time_z1r: list[float] | None = None,
    time_z2r: list[float] | None = None,
    edep_z1r: list[float] | None = None,
    edep_z2r: list[float] | None = None,
) -> dict[str, list[float]]:
    """Create one complete TRAM event with convenient defaults."""
    return {
        "Z1L": [13.0] if z1l is None else z1l,
        "Z2L": [13.1] if z2l is None else z2l,
        "Y1L": [25.0] if y1l is None else y1l,
        "time_Z1L": (
            [1800.0]
            if time_z1l is None
            else time_z1l
        ),
        "time_Z2L": (
            [1820.0]
            if time_z2l is None
            else time_z2l
        ),
        "edep_Z1L": (
            [650.0]
            if edep_z1l is None
            else edep_z1l
        ),
        "edep_Z2L": (
            [720.0]
            if edep_z2l is None
            else edep_z2l
        ),
        "Z1R": [14.0] if z1r is None else z1r,
        "Z2R": [14.1] if z2r is None else z2r,
        "Y1R": [27.0] if y1r is None else y1r,
        "time_Z1R": (
            [1900.0]
            if time_z1r is None
            else time_z1r
        ),
        "time_Z2R": (
            [1930.0]
            if time_z2r is None
            else time_z2r
        ),
        "edep_Z1R": (
            [680.0]
            if edep_z1r is None
            else edep_z1r
        ),
        "edep_Z2R": (
            [740.0]
            if edep_z2r is None
            else edep_z2r
        ),
    }


def expected_from_row(
    row: dict[str, list[float]],
    *,
    left_passes: bool = True,
    right_passes: bool = True,
) -> dict[str, list[float]]:
    def first_or_empty(
        source_column: str,
        passes: bool,
    ) -> list[float]:
        if not passes:
            return []

        source = row[source_column]

        if not source:
            return []

        return [float(source[0])]

    return {
        "StraightZ1L": first_or_empty(
            "Z1L",
            left_passes,
        ),
        "StraightZ2L": first_or_empty(
            "Z2L",
            left_passes,
        ),
        "StraightY1L": first_or_empty(
            "Y1L",
            left_passes,
        ),
        "StraightTimeZ1L": first_or_empty(
            "time_Z1L",
            left_passes,
        ),
        "StraightTimeZ2L": first_or_empty(
            "time_Z2L",
            left_passes,
        ),
        "StraightEdepZ1L": first_or_empty(
            "edep_Z1L",
            left_passes,
        ),
        "StraightEdepZ2L": first_or_empty(
            "edep_Z2L",
            left_passes,
        ),
        "StraightZ1R": first_or_empty(
            "Z1R",
            right_passes,
        ),
        "StraightZ2R": first_or_empty(
            "Z2R",
            right_passes,
        ),
        "StraightY1R": first_or_empty(
            "Y1R",
            right_passes,
        ),
        "StraightTimeZ1R": first_or_empty(
            "time_Z1R",
            right_passes,
        ),
        "StraightTimeZ2R": first_or_empty(
            "time_Z2R",
            right_passes,
        ),
        "StraightEdepZ1R": first_or_empty(
            "edep_Z1R",
            right_passes,
        ),
        "StraightEdepZ2R": first_or_empty(
            "edep_Z2R",
            right_passes,
        ),
    }


def assert_defined(
    rows: list[dict[str, list[float]]],
    settings: dict[str, float | None] | None,
    expected: list[dict[str, list[float]]],
) -> None:
    dataframe = make_dataframe(rows)

    result = (
        define_tram_straight_coincidence_columns(
            [dataframe],
            settings,
        )[0]
    )

    actual = materialize(
        result,
        OUTPUT_COLUMNS,
    )

    assert actual == expected, (
        "\nExpected:\n"
        f"{expected}\n\n"
        "Actual:\n"
        f"{actual}"
    )


# ---------------------------------------------------------------------------
# 1-4: no-op and basic behavior
# ---------------------------------------------------------------------------

def test_01_none_settings_keeps_first_hits():
    row = event()

    assert_defined(
        [row],
        None,
        [expected_from_row(row)],
    )


def test_02_empty_settings_keeps_first_hits():
    row = event()

    assert_defined(
        [row],
        {},
        [expected_from_row(row)],
    )


def test_03_explicit_none_settings_are_ignored():
    row = event()

    settings = {
        "delta_z_max_left": None,
        "z1_min_left": None,
        "z1_max_left": None,
        "z2_min_left": None,
        "z2_max_left": None,
        "z1_edep_min_left": None,
        "z1_edep_max_left": None,
        "z2_edep_min_left": None,
        "z2_edep_max_left": None,
        "z1_time_min_left": None,
        "z1_time_max_left": None,
        "z2_time_min_left": None,
        "z2_time_max_left": None,
        "delta_z_max_right": None,
        "z1_min_right": None,
        "z1_max_right": None,
        "z2_min_right": None,
        "z2_max_right": None,
        "z1_edep_min_right": None,
        "z1_edep_max_right": None,
        "z2_edep_min_right": None,
        "z2_edep_max_right": None,
        "z1_time_min_right": None,
        "z1_time_max_right": None,
        "z2_time_min_right": None,
        "z2_time_max_right": None,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_04_only_first_hit_is_saved():
    row = event(
        z1l=[13.0, 31.0],
        z2l=[13.1, 31.1],
        y1l=[25.0, 35.0],
        time_z1l=[1800.0, 2800.0],
        time_z2l=[1820.0, 2820.0],
        edep_z1l=[650.0, 950.0],
        edep_z2l=[720.0, 1020.0],
        z1r=[14.0, 32.0],
        z2r=[14.1, 32.1],
        y1r=[27.0, 37.0],
        time_z1r=[1900.0, 2900.0],
        time_z2r=[1930.0, 2930.0],
        edep_z1r=[680.0, 980.0],
        edep_z2r=[740.0, 1040.0],
    )

    assert_defined(
        [row],
        {},
        [expected_from_row(row)],
    )


# ---------------------------------------------------------------------------
# 5-16: left-side individual cuts
# ---------------------------------------------------------------------------

LEFT_CASES = [
    (
        "05_delta_z_pass",
        event(z1l=[10.0], z2l=[10.19]),
        {"delta_z_max_left": 0.2},
        True,
    ),
    (
        "06_delta_z_fail",
        event(z1l=[10.0], z2l=[10.21]),
        {"delta_z_max_left": 0.2},
        False,
    ),
    (
        "07_z1_min_pass",
        event(z1l=[10.1]),
        {"z1_min_left": 10.0},
        True,
    ),
    (
        "08_z1_min_boundary_fails",
        event(z1l=[10.0]),
        {"z1_min_left": 10.0},
        False,
    ),
    (
        "09_z1_max_pass",
        event(z1l=[9.9]),
        {"z1_max_left": 10.0},
        True,
    ),
    (
        "10_z1_max_boundary_fails",
        event(z1l=[10.0]),
        {"z1_max_left": 10.0},
        False,
    ),
    (
        "11_z2_min_pass",
        event(z2l=[10.1]),
        {"z2_min_left": 10.0},
        True,
    ),
    (
        "12_z2_max_fail",
        event(z2l=[10.0]),
        {"z2_max_left": 10.0},
        False,
    ),
    (
        "13_z1_edep_min_pass",
        event(edep_z1l=[500.1]),
        {"z1_edep_min_left": 500.0},
        True,
    ),
    (
        "14_z1_edep_max_fail",
        event(edep_z1l=[500.0]),
        {"z1_edep_max_left": 500.0},
        False,
    ),
    (
        "15_z2_edep_min_fail",
        event(edep_z2l=[499.9]),
        {"z2_edep_min_left": 500.0},
        False,
    ),
    (
        "16_z2_edep_max_pass",
        event(edep_z2l=[499.9]),
        {"z2_edep_max_left": 500.0},
        True,
    ),
]


# ---------------------------------------------------------------------------
# 17-20: left-side time cuts
# ---------------------------------------------------------------------------

LEFT_TIME_CASES = [
    (
        "17_z1_time_min_pass",
        event(time_z1l=[1000.1]),
        {"z1_time_min_left": 1000.0},
        True,
    ),
    (
        "18_z1_time_max_fail",
        event(time_z1l=[4000.0]),
        {"z1_time_max_left": 4000.0},
        False,
    ),
    (
        "19_z2_time_min_fail",
        event(time_z2l=[999.9]),
        {"z2_time_min_left": 1000.0},
        False,
    ),
    (
        "20_z2_time_max_pass",
        event(time_z2l=[3999.9]),
        {"z2_time_max_left": 4000.0},
        True,
    ),
]


# ---------------------------------------------------------------------------
# 21-32: right-side individual cuts
# ---------------------------------------------------------------------------

RIGHT_CASES = [
    (
        "21_delta_z_pass",
        event(z1r=[10.0], z2r=[10.19]),
        {"delta_z_max_right": 0.2},
        True,
    ),
    (
        "22_delta_z_fail",
        event(z1r=[10.0], z2r=[10.21]),
        {"delta_z_max_right": 0.2},
        False,
    ),
    (
        "23_z1_min_pass",
        event(z1r=[10.1]),
        {"z1_min_right": 10.0},
        True,
    ),
    (
        "24_z1_max_fail",
        event(z1r=[10.0]),
        {"z1_max_right": 10.0},
        False,
    ),
    (
        "25_z2_min_fail",
        event(z2r=[10.0]),
        {"z2_min_right": 10.0},
        False,
    ),
    (
        "26_z2_max_pass",
        event(z2r=[9.9]),
        {"z2_max_right": 10.0},
        True,
    ),
    (
        "27_z1_edep_min_fail",
        event(edep_z1r=[500.0]),
        {"z1_edep_min_right": 500.0},
        False,
    ),
    (
        "28_z1_edep_max_pass",
        event(edep_z1r=[499.9]),
        {"z1_edep_max_right": 500.0},
        True,
    ),
    (
        "29_z2_edep_min_pass",
        event(edep_z2r=[500.1]),
        {"z2_edep_min_right": 500.0},
        True,
    ),
    (
        "30_z2_edep_max_fail",
        event(edep_z2r=[500.0]),
        {"z2_edep_max_right": 500.0},
        False,
    ),
    (
        "31_z1_time_min_fail",
        event(time_z1r=[1000.0]),
        {"z1_time_min_right": 1000.0},
        False,
    ),
    (
        "32_z2_time_max_pass",
        event(time_z2r=[3999.9]),
        {"z2_time_max_right": 4000.0},
        True,
    ),
]


# ---------------------------------------------------------------------------
# 33-38: complex combined cuts
# ---------------------------------------------------------------------------

def test_33_all_left_cuts_pass():
    row = event(
        z1l=[13.0],
        z2l=[13.1],
        time_z1l=[1800.0],
        time_z2l=[1820.0],
        edep_z1l=[650.0],
        edep_z2l=[720.0],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "z1_min_left": 12.0,
        "z1_max_left": 14.0,
        "z2_min_left": 12.0,
        "z2_max_left": 14.0,
        "z1_edep_min_left": 600.0,
        "z1_edep_max_left": 700.0,
        "z2_edep_min_left": 700.0,
        "z2_edep_max_left": 800.0,
        "z1_time_min_left": 1700.0,
        "z1_time_max_left": 1900.0,
        "z2_time_min_left": 1800.0,
        "z2_time_max_left": 1900.0,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_34_one_left_cut_fails_all_left_outputs_empty():
    row = event(
        z1l=[13.0],
        z2l=[13.1],
        edep_z2l=[699.0],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "z1_min_left": 12.0,
        "z1_max_left": 14.0,
        "z2_edep_min_left": 700.0,
    }

    assert_defined(
        [row],
        settings,
        [
            expected_from_row(
                row,
                left_passes=False,
                right_passes=True,
            )
        ],
    )


def test_35_all_right_cuts_pass():
    row = event(
        z1r=[14.0],
        z2r=[14.1],
        time_z1r=[1900.0],
        time_z2r=[1930.0],
        edep_z1r=[680.0],
        edep_z2r=[740.0],
    )

    settings = {
        "delta_z_max_right": 0.2,
        "z1_min_right": 13.0,
        "z1_max_right": 15.0,
        "z2_min_right": 13.0,
        "z2_max_right": 15.0,
        "z1_edep_min_right": 600.0,
        "z1_edep_max_right": 700.0,
        "z2_edep_min_right": 700.0,
        "z2_edep_max_right": 800.0,
        "z1_time_min_right": 1800.0,
        "z1_time_max_right": 2000.0,
        "z2_time_min_right": 1900.0,
        "z2_time_max_right": 2000.0,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_36_left_passes_right_fails_independently():
    row = event(
        z1l=[13.0],
        z2l=[13.1],
        z1r=[20.0],
        z2r=[14.1],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "delta_z_max_right": 0.2,
    }

    assert_defined(
        [row],
        settings,
        [
            expected_from_row(
                row,
                left_passes=True,
                right_passes=False,
            )
        ],
    )


def test_37_left_fails_right_passes_independently():
    row = event(
        z1l=[20.0],
        z2l=[13.1],
        z1r=[14.0],
        z2r=[14.1],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "delta_z_max_right": 0.2,
    }

    assert_defined(
        [row],
        settings,
        [
            expected_from_row(
                row,
                left_passes=False,
                right_passes=True,
            )
        ],
    )


def test_38_none_disables_only_specific_comparisons():
    row = event(
        z1l=[100.0],
        z2l=[100.1],
        edep_z1l=[1.0],
        edep_z2l=[2.0],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "z1_min_left": None,
        "z1_max_left": None,
        "z1_edep_min_left": None,
        "z2_edep_min_left": None,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


# ---------------------------------------------------------------------------
# 39-43: multiple rows and first-hit edge cases
# ---------------------------------------------------------------------------

def test_39_multiple_rows_receive_independent_results():
    first = event(z1l=[13.0], z2l=[13.1])
    second = event(z1l=[20.0], z2l=[13.1])
    third = event(z1l=[12.5], z2l=[12.6])

    settings = {
        "delta_z_max_left": 0.2,
    }

    assert_defined(
        [first, second, third],
        settings,
        [
            expected_from_row(first),
            expected_from_row(
                second,
                left_passes=False,
            ),
            expected_from_row(third),
        ],
    )


def test_40_second_hit_passes_but_first_hit_fails():
    row = event(
        z1l=[20.0, 13.0],
        z2l=[10.0, 13.1],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "z1_min_left": 12.0,
        "z1_max_left": 14.0,
    }

    assert_defined(
        [row],
        settings,
        [
            expected_from_row(
                row,
                left_passes=False,
            )
        ],
    )


def test_41_first_hit_passes_second_hit_fails():
    row = event(
        z1l=[13.0, 50.0],
        z2l=[13.1, 0.0],
        edep_z1l=[650.0, 10.0],
        edep_z2l=[720.0, 10.0],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "z1_min_left": 12.0,
        "z1_max_left": 14.0,
        "z1_edep_min_left": 500.0,
        "z2_edep_min_left": 500.0,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_42_negative_values_with_optional_ranges():
    row = event(
        z1l=[-2.0],
        z2l=[-2.1],
        time_z1l=[-100.0],
        time_z2l=[-90.0],
        edep_z1l=[-5.0],
        edep_z2l=[-4.0],
    )

    settings = {
        "z1_min_left": -3.0,
        "z1_max_left": -1.0,
        "z2_min_left": -3.0,
        "z2_max_left": -1.0,
        "z1_time_min_left": -200.0,
        "z1_time_max_left": 0.0,
        "z2_time_min_left": -200.0,
        "z2_time_max_left": 0.0,
        "z1_edep_min_left": -10.0,
        "z1_edep_max_left": 0.0,
        "z2_edep_min_left": -10.0,
        "z2_edep_max_left": 0.0,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_43_decimal_precision_near_delta_boundary():
    passing = event(
        z1l=[1.0],
        z2l=[1.199999],
    )
    failing = event(
        z1l=[1.0],
        z2l=[1.200001],
    )

    settings = {
        "delta_z_max_left": 0.2,
    }

    assert_defined(
        [passing, failing],
        settings,
        [
            expected_from_row(passing),
            expected_from_row(
                failing,
                left_passes=False,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# 44-48: failures and multiple dataframes
# ---------------------------------------------------------------------------

def test_44_unknown_setting_raises():
    dataframe = make_dataframe([
        event(),
    ])

    try:
        define_tram_straight_coincidence_columns(
            [dataframe],
            {
                "not_a_real_setting": 1.0,
            },
        )
    except Exception as error:
        message = str(error).lower()

        assert (
            "unknown" in message
            and "not_a_real_setting" in message
        )
    else:
        raise AssertionError(
            "Expected an unknown setting to raise."
        )


def test_45_non_numeric_setting_raises():
    dataframe = make_dataframe([
        event(),
    ])

    try:
        define_tram_straight_coincidence_columns(
            [dataframe],
            {
                "z1_min_left": "bad-value",
            },
        )
    except (TypeError, ValueError):
        pass
    else:
        raise AssertionError(
            "Expected a non-numeric setting to raise."
        )


def test_46_missing_required_input_column_raises():
    dataframe = ROOT.RDataFrame(1)

    for column in INPUT_COLUMNS:
        if column == "Z2R":
            continue

        dataframe = dataframe.Define(
            column,
            "ROOT::VecOps::RVec<double>{1.0}",
        )

    try:
        define_tram_straight_coincidence_columns(
            [dataframe],
            {},
        )
    except Exception as error:
        message = str(error)

        assert "Z2R" in message
        assert "Required branches are missing" in message
    else:
        raise AssertionError(
            "Expected missing Z2R to raise CoincidenceError."
        )


def test_47_two_dataframes_are_processed_independently():
    first_row = event(
        z1l=[13.0],
        z2l=[13.1],
    )
    second_row = event(
        z1l=[20.0],
        z2l=[10.0],
    )

    first = make_dataframe([
        first_row,
    ])
    second = make_dataframe([
        second_row,
    ])

    results = (
        define_tram_straight_coincidence_columns(
            [first, second],
            {
                "delta_z_max_left": 0.2,
            },
        )
    )

    assert materialize(
        results[0],
        OUTPUT_COLUMNS,
    ) == [
        expected_from_row(first_row)
    ]

    assert materialize(
        results[1],
        OUTPUT_COLUMNS,
    ) == [
        expected_from_row(
            second_row,
            left_passes=False,
        )
    ]


def test_48_original_columns_remain_unchanged():
    row = event(
        z1l=[13.0, 30.0],
        z2l=[13.1, 31.0],
    )

    dataframe = make_dataframe([
        row,
    ])

    result = (
        define_tram_straight_coincidence_columns(
            [dataframe],
            {
                "delta_z_max_left": 0.2,
            },
        )[0]
    )

    assert materialize(
        result,
        INPUT_COLUMNS,
    ) == [row]



# ---------------------------------------------------------------------------
# 49-60: larger dataframes and advanced boundary tests
# ---------------------------------------------------------------------------

def test_49_large_dataframe_left_delta_pattern():
    rows = []
    expected = []

    for index in range(100):
        z1 = float(index)
        passes = index % 2 == 0
        z2 = z1 + (0.1 if passes else 0.3)

        row = event(z1l=[z1], z2l=[z2])
        rows.append(row)
        expected.append(
            expected_from_row(
                row,
                left_passes=passes,
            )
        )

    assert_defined(
        rows,
        {"delta_z_max_left": 0.2},
        expected,
    )


def test_50_large_dataframe_both_sides_independent_patterns():
    rows = []
    expected = []

    for index in range(120):
        left_passes = index % 3 != 0
        right_passes = index % 4 != 0

        z1l = 10.0 + index * 0.01
        z1r = 20.0 + index * 0.01

        row = event(
            z1l=[z1l],
            z2l=[z1l + (0.1 if left_passes else 0.4)],
            z1r=[z1r],
            z2r=[z1r + (0.1 if right_passes else 0.4)],
        )

        rows.append(row)
        expected.append(
            expected_from_row(
                row,
                left_passes=left_passes,
                right_passes=right_passes,
            )
        )

    assert_defined(
        rows,
        {
            "delta_z_max_left": 0.2,
            "delta_z_max_right": 0.2,
        },
        expected,
    )


def test_51_strict_boundaries_all_left_fields():
    rows = [
        event(
            z1l=[10.0],
            z2l=[20.0],
            edep_z1l=[100.0],
            edep_z2l=[200.0],
            time_z1l=[1000.0],
            time_z2l=[2000.0],
        ),
        event(
            z1l=[10.000001],
            z2l=[20.000001],
            edep_z1l=[100.000001],
            edep_z2l=[200.000001],
            time_z1l=[1000.000001],
            time_z2l=[2000.000001],
        ),
        event(
            z1l=[19.999999],
            z2l=[29.999999],
            edep_z1l=[199.999999],
            edep_z2l=[299.999999],
            time_z1l=[1999.999999],
            time_z2l=[2999.999999],
        ),
        event(
            z1l=[20.0],
            z2l=[30.0],
            edep_z1l=[200.0],
            edep_z2l=[300.0],
            time_z1l=[2000.0],
            time_z2l=[3000.0],
        ),
    ]

    settings = {
        "z1_min_left": 10.0,
        "z1_max_left": 20.0,
        "z2_min_left": 20.0,
        "z2_max_left": 30.0,
        "z1_edep_min_left": 100.0,
        "z1_edep_max_left": 200.0,
        "z2_edep_min_left": 200.0,
        "z2_edep_max_left": 300.0,
        "z1_time_min_left": 1000.0,
        "z1_time_max_left": 2000.0,
        "z2_time_min_left": 2000.0,
        "z2_time_max_left": 3000.0,
    }

    assert_defined(
        rows,
        settings,
        [
            expected_from_row(rows[0], left_passes=False),
            expected_from_row(rows[1]),
            expected_from_row(rows[2]),
            expected_from_row(rows[3], left_passes=False),
        ],
    )


def test_52_strict_boundaries_all_right_fields():
    rows = [
        event(
            z1r=[10.0],
            z2r=[20.0],
            edep_z1r=[100.0],
            edep_z2r=[200.0],
            time_z1r=[1000.0],
            time_z2r=[2000.0],
        ),
        event(
            z1r=[10.000001],
            z2r=[20.000001],
            edep_z1r=[100.000001],
            edep_z2r=[200.000001],
            time_z1r=[1000.000001],
            time_z2r=[2000.000001],
        ),
        event(
            z1r=[19.999999],
            z2r=[29.999999],
            edep_z1r=[199.999999],
            edep_z2r=[299.999999],
            time_z1r=[1999.999999],
            time_z2r=[2999.999999],
        ),
        event(
            z1r=[20.0],
            z2r=[30.0],
            edep_z1r=[200.0],
            edep_z2r=[300.0],
            time_z1r=[2000.0],
            time_z2r=[3000.0],
        ),
    ]

    settings = {
        "z1_min_right": 10.0,
        "z1_max_right": 20.0,
        "z2_min_right": 20.0,
        "z2_max_right": 30.0,
        "z1_edep_min_right": 100.0,
        "z1_edep_max_right": 200.0,
        "z2_edep_min_right": 200.0,
        "z2_edep_max_right": 300.0,
        "z1_time_min_right": 1000.0,
        "z1_time_max_right": 2000.0,
        "z2_time_min_right": 2000.0,
        "z2_time_max_right": 3000.0,
    }

    assert_defined(
        rows,
        settings,
        [
            expected_from_row(rows[0], right_passes=False),
            expected_from_row(rows[1]),
            expected_from_row(rows[2]),
            expected_from_row(rows[3], right_passes=False),
        ],
    )


def test_53_large_dataframe_full_left_cut_matrix():
    rows = []
    expected = []

    settings = {
        "delta_z_max_left": 0.25,
        "z1_min_left": 5.0,
        "z1_max_left": 35.0,
        "z2_min_left": 5.0,
        "z2_max_left": 35.0,
        "z1_edep_min_left": 500.0,
        "z1_edep_max_left": 1500.0,
        "z2_edep_min_left": 500.0,
        "z2_edep_max_left": 1500.0,
        "z1_time_min_left": 1000.0,
        "z1_time_max_left": 4000.0,
        "z2_time_min_left": 1000.0,
        "z2_time_max_left": 4000.0,
    }

    for index in range(150):
        z1 = float(index % 45)
        z2 = z1 + (0.1 if index % 5 else 0.5)
        e1 = 600.0 + index
        e2 = 700.0 + index
        t1 = 1200.0 + index * 10.0
        t2 = 1250.0 + index * 10.0

        row = event(
            z1l=[z1],
            z2l=[z2],
            edep_z1l=[e1],
            edep_z2l=[e2],
            time_z1l=[t1],
            time_z2l=[t2],
        )

        passes = (
            abs(z1 - z2) < 0.25
            and 5.0 < z1 < 35.0
            and 5.0 < z2 < 35.0
            and 500.0 < e1 < 1500.0
            and 500.0 < e2 < 1500.0
            and 1000.0 < t1 < 4000.0
            and 1000.0 < t2 < 4000.0
        )

        rows.append(row)
        expected.append(
            expected_from_row(
                row,
                left_passes=passes,
            )
        )

    assert_defined(rows, settings, expected)


def test_54_large_dataframe_full_right_cut_matrix():
    rows = []
    expected = []

    settings = {
        "delta_z_max_right": 0.25,
        "z1_min_right": 5.0,
        "z1_max_right": 35.0,
        "z2_min_right": 5.0,
        "z2_max_right": 35.0,
        "z1_edep_min_right": 500.0,
        "z1_edep_max_right": 1500.0,
        "z2_edep_min_right": 500.0,
        "z2_edep_max_right": 1500.0,
        "z1_time_min_right": 1000.0,
        "z1_time_max_right": 4000.0,
        "z2_time_min_right": 1000.0,
        "z2_time_max_right": 4000.0,
    }

    for index in range(150):
        z1 = float(index % 45)
        z2 = z1 + (0.1 if index % 7 else 0.5)
        e1 = 620.0 + index
        e2 = 710.0 + index
        t1 = 1300.0 + index * 9.0
        t2 = 1350.0 + index * 9.0

        row = event(
            z1r=[z1],
            z2r=[z2],
            edep_z1r=[e1],
            edep_z2r=[e2],
            time_z1r=[t1],
            time_z2r=[t2],
        )

        passes = (
            abs(z1 - z2) < 0.25
            and 5.0 < z1 < 35.0
            and 5.0 < z2 < 35.0
            and 500.0 < e1 < 1500.0
            and 500.0 < e2 < 1500.0
            and 1000.0 < t1 < 4000.0
            and 1000.0 < t2 < 4000.0
        )

        rows.append(row)
        expected.append(
            expected_from_row(
                row,
                right_passes=passes,
            )
        )

    assert_defined(rows, settings, expected)


def test_55_none_mixed_with_active_complex_cuts():
    row = event(
        z1l=[13.0],
        z2l=[13.1],
        edep_z1l=[10.0],
        edep_z2l=[20.0],
        time_z1l=[5000.0],
        time_z2l=[6000.0],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "z1_min_left": 12.0,
        "z1_max_left": 14.0,
        "z2_min_left": None,
        "z2_max_left": None,
        "z1_edep_min_left": None,
        "z1_edep_max_left": None,
        "z2_edep_min_left": None,
        "z2_edep_max_left": None,
        "z1_time_min_left": None,
        "z1_time_max_left": None,
        "z2_time_min_left": None,
        "z2_time_max_left": None,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_56_asymmetric_left_and_right_boundaries():
    rows = [
        event(
            z1l=[10.000001],
            z2l=[10.1],
            z1r=[20.0],
            z2r=[20.1],
        ),
        event(
            z1l=[19.999999],
            z2l=[19.9],
            z1r=[29.999999],
            z2r=[29.9],
        ),
        event(
            z1l=[10.0],
            z2l=[10.1],
            z1r=[20.000001],
            z2r=[20.1],
        ),
    ]

    settings = {
        "z1_min_left": 10.0,
        "z1_max_left": 20.0,
        "z1_min_right": 20.0,
        "z1_max_right": 30.0,
    }

    assert_defined(
        rows,
        settings,
        [
            expected_from_row(
                rows[0],
                left_passes=True,
                right_passes=False,
            ),
            expected_from_row(rows[1]),
            expected_from_row(
                rows[2],
                left_passes=False,
                right_passes=True,
            ),
        ],
    )


def test_57_large_multi_hit_dataframe_uses_only_first_hit():
    rows = []
    expected = []

    for index in range(80):
        passes = index % 2 == 0

        row = event(
            z1l=[13.0 if passes else 30.0, 13.0, 13.2],
            z2l=[13.1 if passes else 10.0, 13.1, 13.3],
            edep_z1l=[650.0, 900.0, 950.0],
            edep_z2l=[720.0, 1000.0, 1050.0],
        )

        rows.append(row)
        expected.append(
            expected_from_row(
                row,
                left_passes=passes,
            )
        )

    assert_defined(
        rows,
        {
            "delta_z_max_left": 0.2,
            "z1_min_left": 12.0,
            "z1_max_left": 14.0,
        },
        expected,
    )


def test_58_large_dataframe_sparse_none_configuration():
    rows = []
    expected = []

    settings = {
        "delta_z_max_left": None,
        "z1_min_left": 5.0,
        "z1_max_left": None,
        "z2_min_left": None,
        "z2_max_left": 30.0,
        "z1_edep_min_left": None,
        "z1_edep_max_left": 1000.0,
        "z2_edep_min_left": 400.0,
        "z2_edep_max_left": None,
        "z1_time_min_left": None,
        "z1_time_max_left": 3000.0,
        "z2_time_min_left": 1000.0,
        "z2_time_max_left": None,
    }

    for index in range(90):
        z1 = float(index % 40)
        z2 = float((index * 2) % 40)
        e1 = 500.0 + index * 10.0
        e2 = 300.0 + index * 8.0
        t1 = 500.0 + index * 40.0
        t2 = 700.0 + index * 35.0

        row = event(
            z1l=[z1],
            z2l=[z2],
            edep_z1l=[e1],
            edep_z2l=[e2],
            time_z1l=[t1],
            time_z2l=[t2],
        )

        passes = (
            z1 > 5.0
            and z2 < 30.0
            and e1 < 1000.0
            and e2 > 400.0
            and t1 < 3000.0
            and t2 > 1000.0
        )

        rows.append(row)
        expected.append(
            expected_from_row(
                row,
                left_passes=passes,
            )
        )

    assert_defined(rows, settings, expected)


def test_59_both_sides_all_fields_boundary_mix():
    passing = event(
        z1l=[10.000001],
        z2l=[10.100001],
        edep_z1l=[500.000001],
        edep_z2l=[600.000001],
        time_z1l=[1000.000001],
        time_z2l=[1100.000001],
        z1r=[20.000001],
        z2r=[20.100001],
        edep_z1r=[700.000001],
        edep_z2r=[800.000001],
        time_z1r=[2000.000001],
        time_z2r=[2100.000001],
    )

    failing = event(
        z1l=[20.0],
        z2l=[20.1],
        edep_z1l=[1500.0],
        edep_z2l=[1600.0],
        time_z1l=[4000.0],
        time_z2l=[4100.0],
        z1r=[30.0],
        z2r=[30.1],
        edep_z1r=[1700.0],
        edep_z2r=[1800.0],
        time_z1r=[5000.0],
        time_z2r=[5100.0],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "z1_min_left": 10.0,
        "z1_max_left": 20.0,
        "z2_min_left": 10.0,
        "z2_max_left": 20.5,
        "z1_edep_min_left": 500.0,
        "z1_edep_max_left": 1500.0,
        "z2_edep_min_left": 600.0,
        "z2_edep_max_left": 1600.0,
        "z1_time_min_left": 1000.0,
        "z1_time_max_left": 4000.0,
        "z2_time_min_left": 1100.0,
        "z2_time_max_left": 4100.0,
        "delta_z_max_right": 0.2,
        "z1_min_right": 20.0,
        "z1_max_right": 30.0,
        "z2_min_right": 20.0,
        "z2_max_right": 30.5,
        "z1_edep_min_right": 700.0,
        "z1_edep_max_right": 1700.0,
        "z2_edep_min_right": 800.0,
        "z2_edep_max_right": 1800.0,
        "z1_time_min_right": 2000.0,
        "z1_time_max_right": 5000.0,
        "z2_time_min_right": 2100.0,
        "z2_time_max_right": 5100.0,
    }

    assert_defined(
        [passing, failing],
        settings,
        [
            expected_from_row(passing),
            expected_from_row(
                failing,
                left_passes=False,
                right_passes=False,
            ),
        ],
    )


def test_60_three_large_dataframes_complex_independence():
    groups = []
    expected_groups = []

    for group_index in range(3):
        rows = []
        expected = []

        for row_index in range(60):
            z1l = 12.0 + group_index + row_index * 0.01
            z2l = z1l + (
                0.1
                if row_index % (group_index + 2)
                else 0.35
            )

            z1r = 22.0 + group_index + row_index * 0.01
            z2r = z1r + (
                0.1
                if row_index % (group_index + 3)
                else 0.35
            )

            row = event(
                z1l=[z1l],
                z2l=[z2l],
                z1r=[z1r],
                z2r=[z2r],
            )

            rows.append(row)
            expected.append(
                expected_from_row(
                    row,
                    left_passes=abs(z1l - z2l) < 0.2,
                    right_passes=abs(z1r - z2r) < 0.2,
                )
            )

        groups.append(rows)
        expected_groups.append(expected)

    dataframes = [
        make_dataframe(rows)
        for rows in groups
    ]

    results = define_tram_straight_coincidence_columns(
        dataframes,
        {
            "delta_z_max_left": 0.2,
            "delta_z_max_right": 0.2,
        },
    )

    assert len(results) == 3

    for index, result in enumerate(results):
        assert materialize(
            result,
            OUTPUT_COLUMNS,
        ) == expected_groups[index]



# ---------------------------------------------------------------------------
# 61-80: large numerical values, precision, and large-dataframe stress tests
# ---------------------------------------------------------------------------

def test_61_four_digit_position_values_left():
    row = event(
        z1l=[1234.0],
        z2l=[1234.1],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "z1_min_left": 1200.0,
        "z1_max_left": 1300.0,
        "z2_min_left": 1200.0,
        "z2_max_left": 1300.0,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_62_five_digit_position_values_right():
    row = event(
        z1r=[54321.0],
        z2r=[54321.15],
    )

    settings = {
        "delta_z_max_right": 0.2,
        "z1_min_right": 50000.0,
        "z1_max_right": 60000.0,
        "z2_min_right": 50000.0,
        "z2_max_right": 60000.0,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_63_six_digit_energy_values_left():
    row = event(
        edep_z1l=[123456.0],
        edep_z2l=[654321.0],
    )

    settings = {
        "z1_edep_min_left": 100000.0,
        "z1_edep_max_left": 200000.0,
        "z2_edep_min_left": 600000.0,
        "z2_edep_max_left": 700000.0,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_64_seven_digit_time_values_right():
    row = event(
        time_z1r=[1234567.0],
        time_z2r=[7654321.0],
    )

    settings = {
        "z1_time_min_right": 1000000.0,
        "z1_time_max_right": 2000000.0,
        "z2_time_min_right": 7000000.0,
        "z2_time_max_right": 8000000.0,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_65_eight_digit_position_boundaries():
    passing = event(
        z1l=[10000000.0001],
        z2l=[10000000.1001],
    )

    failing = event(
        z1l=[10000000.0],
        z2l=[10000000.1],
    )

    settings = {
        "z1_min_left": 10000000.0,
    }

    assert_defined(
        [passing, failing],
        settings,
        [
            expected_from_row(passing),
            expected_from_row(
                failing,
                left_passes=False,
            ),
        ],
    )


def test_66_nine_digit_energy_boundaries():
    passing = event(
        edep_z1r=[999999999.0],
    )

    failing = event(
        edep_z1r=[1000000000.0],
    )

    settings = {
        "z1_edep_max_right": 1000000000.0,
    }

    assert_defined(
        [passing, failing],
        settings,
        [
            expected_from_row(passing),
            expected_from_row(
                failing,
                right_passes=False,
            ),
        ],
    )


def test_67_ten_digit_time_values_left():
    row = event(
        time_z1l=[5000000000.0],
        time_z2l=[9000000000.0],
    )

    settings = {
        "z1_time_min_left": 4000000000.0,
        "z1_time_max_left": 6000000000.0,
        "z2_time_min_left": 8000000000.0,
        "z2_time_max_left": 9500000000.0,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_68_large_delta_z_comparison():
    passing = event(
        z1l=[9999999999.0],
        z2l=[9999999999.19],
    )

    failing = event(
        z1l=[9999999999.0],
        z2l=[9999999999.21],
    )

    settings = {
        "delta_z_max_left": 0.2,
    }

    assert_defined(
        [passing, failing],
        settings,
        [
            expected_from_row(passing),
            expected_from_row(
                failing,
                left_passes=False,
            ),
        ],
    )


def test_69_large_values_both_sides_all_fields():
    row = event(
        z1l=[1234567890.0],
        z2l=[1234567890.1],
        edep_z1l=[2345678901.0],
        edep_z2l=[3456789012.0],
        time_z1l=[4567890123.0],
        time_z2l=[5678901234.0],
        z1r=[6789012345.0],
        z2r=[6789012345.1],
        edep_z1r=[7890123456.0],
        edep_z2r=[8901234567.0],
        time_z1r=[9012345678.0],
        time_z2r=[9123456789.0],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "z1_min_left": 1000000000.0,
        "z1_max_left": 2000000000.0,
        "z2_min_left": 1000000000.0,
        "z2_max_left": 2000000000.0,
        "z1_edep_min_left": 2000000000.0,
        "z1_edep_max_left": 3000000000.0,
        "z2_edep_min_left": 3000000000.0,
        "z2_edep_max_left": 4000000000.0,
        "z1_time_min_left": 4000000000.0,
        "z1_time_max_left": 5000000000.0,
        "z2_time_min_left": 5000000000.0,
        "z2_time_max_left": 6000000000.0,
        "delta_z_max_right": 0.2,
        "z1_min_right": 6000000000.0,
        "z1_max_right": 7000000000.0,
        "z2_min_right": 6000000000.0,
        "z2_max_right": 7000000000.0,
        "z1_edep_min_right": 7000000000.0,
        "z1_edep_max_right": 8000000000.0,
        "z2_edep_min_right": 8000000000.0,
        "z2_edep_max_right": 9000000000.0,
        "z1_time_min_right": 9000000000.0,
        "z1_time_max_right": 9100000000.0,
        "z2_time_min_right": 9100000000.0,
        "z2_time_max_right": 9200000000.0,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_70_large_values_one_condition_fails():
    row = event(
        z1l=[1234567890.0],
        z2l=[1234567890.1],
        edep_z1l=[2345678901.0],
        edep_z2l=[3456789012.0],
        time_z1l=[4567890123.0],
        time_z2l=[5678901234.0],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "z1_edep_min_left": 3000000000.0,
    }

    assert_defined(
        [row],
        settings,
        [
            expected_from_row(
                row,
                left_passes=False,
            )
        ],
    )


def test_71_large_dataframe_1000_rows_four_to_ten_digits():
    rows = []
    expected = []

    for index in range(1000):
        base = 1000.0 + index * 10000000.0
        passes = index % 5 != 0

        row = event(
            z1l=[base],
            z2l=[
                base + (
                    0.1
                    if passes
                    else 0.5
                )
            ],
            edep_z1l=[base + 2000.0],
            edep_z2l=[base + 3000.0],
            time_z1l=[base + 4000.0],
            time_z2l=[base + 5000.0],
        )

        rows.append(row)
        expected.append(
            expected_from_row(
                row,
                left_passes=passes,
            )
        )

    assert_defined(
        rows,
        {
            "delta_z_max_left": 0.2,
        },
        expected,
    )


def test_72_large_dataframe_1200_rows_both_sides():
    rows = []
    expected = []

    for index in range(1200):
        left_base = 10000.0 + index * 1000000.0
        right_base = 20000.0 + index * 2000000.0

        left_passes = index % 7 != 0
        right_passes = index % 11 != 0

        row = event(
            z1l=[left_base],
            z2l=[
                left_base + (
                    0.1
                    if left_passes
                    else 0.4
                )
            ],
            z1r=[right_base],
            z2r=[
                right_base + (
                    0.1
                    if right_passes
                    else 0.4
                )
            ],
        )

        rows.append(row)
        expected.append(
            expected_from_row(
                row,
                left_passes=left_passes,
                right_passes=right_passes,
            )
        )

    assert_defined(
        rows,
        {
            "delta_z_max_left": 0.2,
            "delta_z_max_right": 0.2,
        },
        expected,
    )


def test_73_large_dataframe_dense_numeric_ranges():
    rows = []
    expected = []

    settings = {
        "z1_min_left": 1000000.0,
        "z1_max_left": 9000000000.0,
        "z2_min_left": 1000000.0,
        "z2_max_left": 9000000000.0,
        "z1_edep_min_left": 2000000.0,
        "z1_edep_max_left": 8000000000.0,
        "z2_edep_min_left": 3000000.0,
        "z2_edep_max_left": 7000000000.0,
        "z1_time_min_left": 4000000.0,
        "z1_time_max_left": 6000000000.0,
        "z2_time_min_left": 5000000.0,
        "z2_time_max_left": 5000000000.0,
    }

    for index in range(500):
        scale = float(index + 1) * 10000000.0

        row = event(
            z1l=[scale],
            z2l=[scale + 1.0],
            edep_z1l=[scale + 2.0],
            edep_z2l=[scale + 3.0],
            time_z1l=[scale + 4.0],
            time_z2l=[scale + 5.0],
        )

        passes = (
            1000000.0 < scale < 9000000000.0
            and 1000000.0 < scale + 1.0 < 9000000000.0
            and 2000000.0 < scale + 2.0 < 8000000000.0
            and 3000000.0 < scale + 3.0 < 7000000000.0
            and 4000000.0 < scale + 4.0 < 6000000000.0
            and 5000000.0 < scale + 5.0 < 5000000000.0
        )

        rows.append(row)
        expected.append(
            expected_from_row(
                row,
                left_passes=passes,
            )
        )

    assert_defined(
        rows,
        settings,
        expected,
    )


def test_74_large_dataframe_right_numeric_ranges():
    rows = []
    expected = []

    settings = {
        "z1_min_right": 1000000.0,
        "z1_max_right": 9000000000.0,
        "z2_min_right": 1000000.0,
        "z2_max_right": 9000000000.0,
        "z1_edep_min_right": 2000000.0,
        "z1_edep_max_right": 8000000000.0,
        "z2_edep_min_right": 3000000.0,
        "z2_edep_max_right": 7000000000.0,
        "z1_time_min_right": 4000000.0,
        "z1_time_max_right": 6000000000.0,
        "z2_time_min_right": 5000000.0,
        "z2_time_max_right": 5000000000.0,
    }

    for index in range(500):
        scale = float(index + 1) * 10000000.0

        row = event(
            z1r=[scale],
            z2r=[scale + 1.0],
            edep_z1r=[scale + 2.0],
            edep_z2r=[scale + 3.0],
            time_z1r=[scale + 4.0],
            time_z2r=[scale + 5.0],
        )

        passes = (
            1000000.0 < scale < 9000000000.0
            and 1000000.0 < scale + 1.0 < 9000000000.0
            and 2000000.0 < scale + 2.0 < 8000000000.0
            and 3000000.0 < scale + 3.0 < 7000000000.0
            and 4000000.0 < scale + 4.0 < 6000000000.0
            and 5000000.0 < scale + 5.0 < 5000000000.0
        )

        rows.append(row)
        expected.append(
            expected_from_row(
                row,
                right_passes=passes,
            )
        )

    assert_defined(
        rows,
        settings,
        expected,
    )


def test_75_precision_near_large_minimum_boundary():
    passing = event(
        z1l=[1000000000.0001],
    )

    failing = event(
        z1l=[1000000000.0],
    )

    settings = {
        "z1_min_left": 1000000000.0,
    }

    assert_defined(
        [passing, failing],
        settings,
        [
            expected_from_row(passing),
            expected_from_row(
                failing,
                left_passes=False,
            ),
        ],
    )


def test_76_precision_near_large_maximum_boundary():
    passing = event(
        time_z2r=[9999999999.999],
    )

    failing = event(
        time_z2r=[10000000000.0],
    )

    settings = {
        "z2_time_max_right": 10000000000.0,
    }

    assert_defined(
        [passing, failing],
        settings,
        [
            expected_from_row(passing),
            expected_from_row(
                failing,
                right_passes=False,
            ),
        ],
    )


def test_77_multiple_large_dataframes():
    dataframes = []
    expected_groups = []

    for group_index in range(5):
        rows = []
        expected = []

        for row_index in range(200):
            base = (
                100000.0
                + group_index * 1000000000.0
                + row_index * 1000000.0
            )

            passes = row_index % (group_index + 2) != 0

            row = event(
                z1l=[base],
                z2l=[
                    base + (
                        0.1
                        if passes
                        else 0.3
                    )
                ],
            )

            rows.append(row)
            expected.append(
                expected_from_row(
                    row,
                    left_passes=passes,
                )
            )

        dataframes.append(
            make_dataframe(rows)
        )
        expected_groups.append(expected)

    results = (
        define_tram_straight_coincidence_columns(
            dataframes,
            {
                "delta_z_max_left": 0.2,
            },
        )
    )

    assert len(results) == 5

    for index, result in enumerate(results):
        assert materialize(
            result,
            OUTPUT_COLUMNS,
        ) == expected_groups[index]


def test_78_large_multihit_values_only_first_used():
    row = event(
        z1l=[
            9999999999.0,
            1234.0,
            5678.0,
        ],
        z2l=[
            9999999999.5,
            1234.1,
            5678.1,
        ],
        edep_z1l=[
            9999999999.0,
            1000.0,
            2000.0,
        ],
        edep_z2l=[
            9999999999.0,
            1100.0,
            2100.0,
        ],
    )

    settings = {
        "delta_z_max_left": 0.2,
        "z1_min_left": 1000.0,
        "z1_max_left": 2000.0,
    }

    assert_defined(
        [row],
        settings,
        [
            expected_from_row(
                row,
                left_passes=False,
            )
        ],
    )


def test_79_large_values_with_many_none_settings():
    row = event(
        z1r=[8765432109.0],
        z2r=[8765432109.1],
        edep_z1r=[7654321098.0],
        edep_z2r=[6543210987.0],
        time_z1r=[5432109876.0],
        time_z2r=[4321098765.0],
    )

    settings = {
        "delta_z_max_right": 0.2,
        "z1_min_right": None,
        "z1_max_right": None,
        "z2_min_right": None,
        "z2_max_right": None,
        "z1_edep_min_right": None,
        "z1_edep_max_right": None,
        "z2_edep_min_right": None,
        "z2_edep_max_right": None,
        "z1_time_min_right": None,
        "z1_time_max_right": None,
        "z2_time_min_right": None,
        "z2_time_max_right": None,
    }

    assert_defined(
        [row],
        settings,
        [expected_from_row(row)],
    )


def test_80_stress_2000_rows_full_both_side_logic():
    rows = []
    expected = []

    settings = {
        "delta_z_max_left": 0.2,
        "delta_z_max_right": 0.2,
        "z1_min_left": 1000.0,
        "z1_max_left": 9999999999.0,
        "z2_min_left": 1000.0,
        "z2_max_left": 9999999999.0,
        "z1_edep_min_left": 1000.0,
        "z1_edep_max_left": 9999999999.0,
        "z2_edep_min_left": 1000.0,
        "z2_edep_max_left": 9999999999.0,
        "z1_time_min_left": 1000.0,
        "z1_time_max_left": 9999999999.0,
        "z2_time_min_left": 1000.0,
        "z2_time_max_left": 9999999999.0,
        "z1_min_right": 1000.0,
        "z1_max_right": 9999999999.0,
        "z2_min_right": 1000.0,
        "z2_max_right": 9999999999.0,
        "z1_edep_min_right": 1000.0,
        "z1_edep_max_right": 9999999999.0,
        "z2_edep_min_right": 1000.0,
        "z2_edep_max_right": 9999999999.0,
        "z1_time_min_right": 1000.0,
        "z1_time_max_right": 9999999999.0,
        "z2_time_min_right": 1000.0,
        "z2_time_max_right": 9999999999.0,
    }

    for index in range(2000):
        base = 10000.0 + index * 1000000.0

        left_passes = index % 13 != 0
        right_passes = index % 17 != 0

        row = event(
            z1l=[base],
            z2l=[
                base + (
                    0.1
                    if left_passes
                    else 0.5
                )
            ],
            edep_z1l=[base + 100.0],
            edep_z2l=[base + 200.0],
            time_z1l=[base + 300.0],
            time_z2l=[base + 400.0],
            z1r=[base + 500.0],
            z2r=[
                base
                + 500.0
                + (
                    0.1
                    if right_passes
                    else 0.5
                )
            ],
            edep_z1r=[base + 600.0],
            edep_z2r=[base + 700.0],
            time_z1r=[base + 800.0],
            time_z2r=[base + 900.0],
        )

        rows.append(row)
        expected.append(
            expected_from_row(
                row,
                left_passes=left_passes,
                right_passes=right_passes,
            )
        )

    assert_defined(
        rows,
        settings,
        expected,
    )


# ---------------------------------------------------------------------------
# Case collection
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 81-120: sparse / empty-branch semantics for the rewritten implementation
#
# New policy under test:
#   * only branches referenced by ACTIVE cuts are required to be non-empty;
#   * output-only branches may be empty without making the side fail;
#   * an empty source branch produces [] only for its own Straight... output;
#   * if an ACTIVE cut needs an empty source branch, that side fails;
#   * left and right sides remain independent.
# ---------------------------------------------------------------------------

SPARSE_BRANCH_CASES = [
    # ------------------------------------------------------------------
    # 81-88: left side passes although output-only branches are empty.
    # ------------------------------------------------------------------
    (
        "test_81_left_y1_empty_does_not_fail_delta_cut",
        event(y1l=[]),
        {"delta_z_max_left": 0.2},
        True,
        True,
    ),
    (
        "test_82_left_time_z2_empty_does_not_fail_z1_cut",
        event(time_z2l=[]),
        {"z1_min_left": 12.0, "z1_max_left": 14.0},
        True,
        True,
    ),
    (
        "test_83_left_edep_z2_empty_does_not_fail_z1_position_cut",
        event(edep_z2l=[]),
        {"z1_min_left": 12.0},
        True,
        True,
    ),
    (
        "test_84_left_y1_and_time_z2_empty_still_pass",
        event(y1l=[], time_z2l=[]),
        {
            "delta_z_max_left": 0.2,
            "z1_min_left": 12.0,
            "z1_time_min_left": 1700.0,
        },
        True,
        True,
    ),
    (
        "test_85_left_multiple_output_only_branches_empty",
        event(
            y1l=[],
            time_z2l=[],
            edep_z2l=[],
        ),
        {
            "z1_min_left": 12.0,
            "z1_max_left": 14.0,
            "z1_time_min_left": 1700.0,
            "z1_edep_min_left": 600.0,
        },
        True,
        True,
    ),
    (
        "test_86_left_z2_empty_allowed_when_no_active_cut_uses_z2",
        event(z2l=[]),
        {"z1_min_left": 12.0},
        True,
        True,
    ),
    (
        "test_87_left_z1_empty_allowed_when_only_z2_cut_active",
        event(z1l=[]),
        {"z2_min_left": 12.0},
        True,
        True,
    ),
    (
        "test_88_left_all_non_cut_outputs_empty",
        event(
            y1l=[],
            time_z2l=[],
            edep_z2l=[],
        ),
        {"z1_time_min_left": 1700.0},
        True,
        True,
    ),

    # ------------------------------------------------------------------
    # 89-96: right side passes although output-only branches are empty.
    # ------------------------------------------------------------------
    (
        "test_89_right_y1_empty_does_not_fail_delta_cut",
        event(y1r=[]),
        {"delta_z_max_right": 0.2},
        True,
        True,
    ),
    (
        "test_90_right_time_z2_empty_does_not_fail_z1_cut",
        event(time_z2r=[]),
        {"z1_min_right": 13.0, "z1_max_right": 15.0},
        True,
        True,
    ),
    (
        "test_91_right_edep_z2_empty_does_not_fail_z1_position_cut",
        event(edep_z2r=[]),
        {"z1_min_right": 13.0},
        True,
        True,
    ),
    (
        "test_92_right_y1_and_time_z2_empty_still_pass",
        event(y1r=[], time_z2r=[]),
        {
            "delta_z_max_right": 0.2,
            "z1_min_right": 13.0,
            "z1_time_min_right": 1800.0,
        },
        True,
        True,
    ),
    (
        "test_93_right_multiple_output_only_branches_empty",
        event(
            y1r=[],
            time_z2r=[],
            edep_z2r=[],
        ),
        {
            "z1_min_right": 13.0,
            "z1_max_right": 15.0,
            "z1_time_min_right": 1800.0,
            "z1_edep_min_right": 600.0,
        },
        True,
        True,
    ),
    (
        "test_94_right_z2_empty_allowed_when_no_active_cut_uses_z2",
        event(z2r=[]),
        {"z1_min_right": 13.0},
        True,
        True,
    ),
    (
        "test_95_right_z1_empty_allowed_when_only_z2_cut_active",
        event(z1r=[]),
        {"z2_min_right": 13.0},
        True,
        True,
    ),
    (
        "test_96_right_all_non_cut_outputs_empty",
        event(
            y1r=[],
            time_z2r=[],
            edep_z2r=[],
        ),
        {"z1_time_min_right": 1800.0},
        True,
        True,
    ),

    # ------------------------------------------------------------------
    # 97-108: empty branch referenced by an active cut MUST fail that side.
    # ------------------------------------------------------------------
    (
        "test_97_empty_z1l_fails_active_z1_min_cut",
        event(z1l=[]),
        {"z1_min_left": 12.0},
        False,
        True,
    ),
    (
        "test_98_empty_z2l_fails_active_z2_max_cut",
        event(z2l=[]),
        {"z2_max_left": 14.0},
        False,
        True,
    ),
    (
        "test_99_empty_z1l_fails_active_delta_cut",
        event(z1l=[]),
        {"delta_z_max_left": 0.2},
        False,
        True,
    ),
    (
        "test_100_empty_z2l_fails_active_delta_cut",
        event(z2l=[]),
        {"delta_z_max_left": 0.2},
        False,
        True,
    ),
    (
        "test_101_empty_edep_z1l_fails_active_edep_cut",
        event(edep_z1l=[]),
        {"z1_edep_min_left": 500.0},
        False,
        True,
    ),
    (
        "test_102_empty_time_z2l_fails_active_time_cut",
        event(time_z2l=[]),
        {"z2_time_max_left": 4000.0},
        False,
        True,
    ),
    (
        "test_103_empty_z1r_fails_active_z1_cut",
        event(z1r=[]),
        {"z1_min_right": 13.0},
        True,
        False,
    ),
    (
        "test_104_empty_z2r_fails_active_delta_cut",
        event(z2r=[]),
        {"delta_z_max_right": 0.2},
        True,
        False,
    ),
    (
        "test_105_empty_edep_z1r_fails_active_edep_cut",
        event(edep_z1r=[]),
        {"z1_edep_max_right": 1000.0},
        True,
        False,
    ),
    (
        "test_106_empty_edep_z2r_fails_active_edep_cut",
        event(edep_z2r=[]),
        {"z2_edep_min_right": 500.0},
        True,
        False,
    ),
    (
        "test_107_empty_time_z1r_fails_active_time_cut",
        event(time_z1r=[]),
        {"z1_time_min_right": 1000.0},
        True,
        False,
    ),
    (
        "test_108_empty_time_z2r_fails_active_time_cut",
        event(time_z2r=[]),
        {"z2_time_max_right": 4000.0},
        True,
        False,
    ),

    # ------------------------------------------------------------------
    # 109-116: mixed left/right sparse events and side independence.
    # ------------------------------------------------------------------
    (
        "test_109_left_passes_with_empty_y1_while_right_fails_delta",
        event(
            y1l=[],
            z1r=[20.0],
            z2r=[14.0],
        ),
        {
            "delta_z_max_left": 0.2,
            "delta_z_max_right": 0.2,
        },
        True,
        False,
    ),
    (
        "test_110_right_passes_with_empty_y1_while_left_fails_delta",
        event(
            y1r=[],
            z1l=[20.0],
            z2l=[13.0],
        ),
        {
            "delta_z_max_left": 0.2,
            "delta_z_max_right": 0.2,
        },
        False,
        True,
    ),
    (
        "test_111_both_sides_pass_with_empty_output_only_y_columns",
        event(
            y1l=[],
            y1r=[],
        ),
        {
            "delta_z_max_left": 0.2,
            "delta_z_max_right": 0.2,
        },
        True,
        True,
    ),
    (
        "test_112_both_sides_pass_with_empty_output_only_time_z2",
        event(
            time_z2l=[],
            time_z2r=[],
        ),
        {
            "z1_time_min_left": 1700.0,
            "z1_time_min_right": 1800.0,
        },
        True,
        True,
    ),
    (
        "test_113_left_active_source_empty_right_output_only_empty",
        event(
            z1l=[],
            y1r=[],
        ),
        {
            "z1_min_left": 12.0,
            "z1_min_right": 13.0,
        },
        False,
        True,
    ),
    (
        "test_114_right_active_source_empty_left_output_only_empty",
        event(
            y1l=[],
            z1r=[],
        ),
        {
            "z1_min_left": 12.0,
            "z1_min_right": 13.0,
        },
        True,
        False,
    ),
    (
        "test_115_left_z2_empty_but_only_z1_cut_right_delta_passes",
        event(
            z2l=[],
            y1r=[],
        ),
        {
            "z1_min_left": 12.0,
            "delta_z_max_right": 0.2,
        },
        True,
        True,
    ),
    (
        "test_116_right_z2_empty_but_only_z1_cut_left_delta_passes",
        event(
            y1l=[],
            z2r=[],
        ),
        {
            "delta_z_max_left": 0.2,
            "z1_min_right": 13.0,
        },
        True,
        True,
    ),

    # ------------------------------------------------------------------
    # 117-120: no active cuts and very sparse rows.
    # With no active cuts, side condition is true. Each output independently
    # returns [first] or [] depending on its own source vector.
    # ------------------------------------------------------------------
    (
        "test_117_no_active_cuts_left_sparse_outputs_preserved_individually",
        event(
            z1l=[],
            y1l=[],
            time_z2l=[],
            edep_z1l=[],
        ),
        {},
        True,
        True,
    ),
    (
        "test_118_no_active_cuts_right_sparse_outputs_preserved_individually",
        event(
            z2r=[],
            y1r=[],
            time_z1r=[],
            edep_z2r=[],
        ),
        {},
        True,
        True,
    ),
    (
        "test_119_no_active_cuts_both_sides_mixed_sparse_outputs",
        event(
            z2l=[],
            y1l=[],
            time_z1l=[],
            z1r=[],
            time_z2r=[],
            edep_z1r=[],
        ),
        None,
        True,
        True,
    ),
    (
        "test_120_no_active_cuts_all_input_vectors_empty",
        event(
            z1l=[],
            z2l=[],
            y1l=[],
            time_z1l=[],
            time_z2l=[],
            edep_z1l=[],
            edep_z2l=[],
            z1r=[],
            z2r=[],
            y1r=[],
            time_z1r=[],
            time_z2r=[],
            edep_z1r=[],
            edep_z2r=[],
        ),
        {},
        True,
        True,
    ),
]


def _run_sparse_branch_cases():
    tests = []

    for (
        case_name,
        row,
        settings,
        left_passes,
        right_passes,
    ) in SPARSE_BRANCH_CASES:

        def run_case(
            row=row,
            settings=settings,
            left_passes=left_passes,
            right_passes=right_passes,
        ):
            assert_defined(
                [row],
                settings,
                [
                    expected_from_row(
                        row,
                        left_passes=left_passes,
                        right_passes=right_passes,
                    )
                ],
            )

        run_case.__name__ = case_name

        tests.append(
            (
                case_name,
                run_case,
            )
        )

    assert len(tests) == 40
    return tests


def _run_side_cases(
    cases,
    *,
    side: str,
):
    tests = []

    for (
        case_name,
        row,
        settings,
        passes,
    ) in cases:
        def run_case(
            row=row,
            settings=settings,
            passes=passes,
            side=side,
        ):
            expected = expected_from_row(
                row,
                left_passes=(
                    passes
                    if side == "left"
                    else True
                ),
                right_passes=(
                    passes
                    if side == "right"
                    else True
                ),
            )

            assert_defined(
                [row],
                settings,
                [expected],
            )

        tests.append((
            case_name,
            run_case,
        ))

    return tests


def collect_tests():
    tests = [
        (
            test_01_none_settings_keeps_first_hits.__name__,
            test_01_none_settings_keeps_first_hits,
        ),
        (
            test_02_empty_settings_keeps_first_hits.__name__,
            test_02_empty_settings_keeps_first_hits,
        ),
        (
            test_03_explicit_none_settings_are_ignored.__name__,
            test_03_explicit_none_settings_are_ignored,
        ),
        (
            test_04_only_first_hit_is_saved.__name__,
            test_04_only_first_hit_is_saved,
        ),
    ]

    tests.extend(
        _run_side_cases(
            LEFT_CASES,
            side="left",
        )
    )

    tests.extend(
        _run_side_cases(
            LEFT_TIME_CASES,
            side="left",
        )
    )

    tests.extend(
        _run_side_cases(
            RIGHT_CASES,
            side="right",
        )
    )

    standalone_tests = [
        test_33_all_left_cuts_pass,
        test_34_one_left_cut_fails_all_left_outputs_empty,
        test_35_all_right_cuts_pass,
        test_36_left_passes_right_fails_independently,
        test_37_left_fails_right_passes_independently,
        test_38_none_disables_only_specific_comparisons,
        test_39_multiple_rows_receive_independent_results,
        test_40_second_hit_passes_but_first_hit_fails,
        test_41_first_hit_passes_second_hit_fails,
        test_42_negative_values_with_optional_ranges,
        test_43_decimal_precision_near_delta_boundary,
        test_44_unknown_setting_raises,
        test_45_non_numeric_setting_raises,
        test_46_missing_required_input_column_raises,
        test_47_two_dataframes_are_processed_independently,
        test_48_original_columns_remain_unchanged,
        test_49_large_dataframe_left_delta_pattern,
        test_50_large_dataframe_both_sides_independent_patterns,
        test_51_strict_boundaries_all_left_fields,
        test_52_strict_boundaries_all_right_fields,
        test_53_large_dataframe_full_left_cut_matrix,
        test_54_large_dataframe_full_right_cut_matrix,
        test_55_none_mixed_with_active_complex_cuts,
        test_56_asymmetric_left_and_right_boundaries,
        test_57_large_multi_hit_dataframe_uses_only_first_hit,
        test_58_large_dataframe_sparse_none_configuration,
        test_59_both_sides_all_fields_boundary_mix,
        test_60_three_large_dataframes_complex_independence,
        test_61_four_digit_position_values_left,
        test_62_five_digit_position_values_right,
        test_63_six_digit_energy_values_left,
        test_64_seven_digit_time_values_right,
        test_65_eight_digit_position_boundaries,
        test_66_nine_digit_energy_boundaries,
        test_67_ten_digit_time_values_left,
        test_68_large_delta_z_comparison,
        test_69_large_values_both_sides_all_fields,
        test_70_large_values_one_condition_fails,
        test_71_large_dataframe_1000_rows_four_to_ten_digits,
        test_72_large_dataframe_1200_rows_both_sides,
        test_73_large_dataframe_dense_numeric_ranges,
        test_74_large_dataframe_right_numeric_ranges,
        test_75_precision_near_large_minimum_boundary,
        test_76_precision_near_large_maximum_boundary,
        test_77_multiple_large_dataframes,
        test_78_large_multihit_values_only_first_used,
        test_79_large_values_with_many_none_settings,
        test_80_stress_2000_rows_full_both_side_logic,
    ]

    tests.extend(
        (test.__name__, test)
        for test in standalone_tests
    )

    tests.extend(
        _run_sparse_branch_cases()
    )

    assert len(tests) == 120, (
        f"Test suite must contain exactly 120 tests, got {len(tests)}."
    )

    return tests


def run_all_tests() -> int:
    tests = collect_tests()
    passed = 0
    failures = []

    print(
        "Running "
        f"{len(tests)} "
        "define_tram_straight_coincidence_columns "
        "tests...\n"
    )

    for index, (name, test) in enumerate(
        tests,
        start=1,
    ):
        try:
            test()
        except Exception as error:
            failures.append(
                (name, error)
            )

            print(
                f"[{index:02d}/{len(tests):02d}] "
                f"FAIL  {name}: "
                f"{type(error).__name__}: "
                f"{error}"
            )
        else:
            passed += 1

            print(
                f"[{index:02d}/{len(tests):02d}] "
                f"PASS  {name}"
            )

    print("\n" + "=" * 72)
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")
    print(f"Total:  {len(tests)}")

    if failures:
        print("\nFailure details:")

        for name, error in failures:
            print(
                f"  - {name}: "
                f"{type(error).__name__}: "
                f"{error}"
            )

        return 1

    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(
        run_all_tests()
    )