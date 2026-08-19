"""
150 standalone black-box tests for detector_filter_cut_rdataframe.

Every test follows the same contract:

    known input ROOT.RDataFrame(s)
        -> detector_filter_cut_rdataframe(...)
        -> materialize output
        -> compare with explicitly known expected output

No implementation detail of detector_filter_cut_rdataframe is inspected.

Run with:

    python test_detector_filter_cut_rdataframe_standalone.py

IMPORTANT:
    The import below assumes detector_filter_cut_rdataframe lives in
    Helpers.Filter.general_apply_filter next to global_filter_cut_rdataframe.
    If you put it in another module, change ONLY that import.
"""

from __future__ import annotations

from typing import Any
import math
import os
import sys

import ROOT


# ---------------------------------------------------------------------------
# Import function under test
# ---------------------------------------------------------------------------

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from Helpers.Filter.filter_per_detector import (
    detector_filter_cut_rdataframe,
)


# ===========================================================================
# Input RDataFrame construction
# ===========================================================================


class CharArray:
    """Marker used only by the test-data builder for RVec<Char_t> strings."""

    def __init__(self, value: str):
        self.value = value


def _escape_cpp_string(value: str) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
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
            return (
                "std::numeric_limits<double>::infinity()"
                if value > 0
                else "-std::numeric_limits<double>::infinity()"
            )

        return repr(value)

    if isinstance(value, str):
        return 'std::string{"' + _escape_cpp_string(value) + '"}'

    raise TypeError(f"Unsupported scalar test value: {value!r}")


def _infer_vector_cpp_type(all_rows: list[list[Any]]) -> str:
    flattened = [
        value
        for row in all_rows
        for value in row
    ]

    if not flattened:
        return "int"

    if all(isinstance(value, bool) for value in flattened):
        return "bool"

    if all(isinstance(value, str) for value in flattened):
        return "std::string"

    if any(isinstance(value, float) for value in flattened):
        return "double"

    return "int"


def _cpp_vector(values: list[Any], cpp_type: str) -> str:
    body = ", ".join(_cpp_scalar(value) for value in values)
    return f"ROOT::VecOps::RVec<{cpp_type}>{{{body}}}"


def _cpp_char_array(value: str) -> str:
    encoded = value.encode("utf-8")
    values = [str(byte) for byte in encoded]
    values.append("0")
    return "ROOT::VecOps::RVec<Char_t>{" + ", ".join(values) + "}"


def _column_expression(values: list[Any]) -> str:
    first = values[0]

    if isinstance(first, CharArray):
        literals = [
            _cpp_char_array(value.value)
            for value in values
        ]
        fallback = "ROOT::VecOps::RVec<Char_t>{0}"

    elif isinstance(first, (list, tuple)):
        rows = [list(value) for value in values]
        cpp_type = _infer_vector_cpp_type(rows)
        literals = [
            _cpp_vector(row, cpp_type)
            for row in rows
        ]
        fallback = f"ROOT::VecOps::RVec<{cpp_type}>{{}}"

    else:
        literals = [_cpp_scalar(value) for value in values]

        if isinstance(first, str):
            fallback = 'std::string{""}'
        elif isinstance(first, bool):
            fallback = "false"
        elif isinstance(first, float):
            fallback = "0.0"
        else:
            fallback = "0"

    expression = fallback

    for index in reversed(range(len(literals))):
        expression = (
            f"(rdfentry_ == {index}ULL ? "
            f"{literals[index]} : "
            f"{expression})"
        )

    return expression


def make_dataframe(rows: list[dict[str, Any]]):
    assert rows

    columns = list(rows[0])

    assert all(
        list(row) == columns
        for row in rows
    )

    dataframe = ROOT.RDataFrame(len(rows))

    for column in columns:
        dataframe = dataframe.Define(
            column,
            _column_expression(
                [row[column] for row in rows]
            ),
        )

    return dataframe


# ===========================================================================
# Result conversion
# ===========================================================================


def _python_value(value: Any) -> Any:
    if isinstance(value, str):
        return value

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    if hasattr(value, "tolist"):
        return _python_value(value.tolist())

    if hasattr(value, "item"):
        converted = value.item()
        if converted is not value:
            return _python_value(converted)

    if isinstance(value, (list, tuple)):
        return [_python_value(item) for item in value]

    try:
        return [_python_value(item) for item in value]
    except TypeError:
        return value


def materialize(
    dataframe,
    columns: list[str],
) -> list[dict[str, Any]]:
    arrays = dataframe.AsNumpy(columns)

    if not columns:
        return []

    count = len(arrays[columns[0]])

    return [
        {
            column: _python_value(arrays[column][row])
            for column in columns
        }
        for row in range(count)
    ]


# ===========================================================================
# Black-box check helpers
# ===========================================================================


def check_detector_filter(
    rows: list[dict[str, Any]],
    detectors: str | list[str],
    cut_filters: str | list[str],
    expected: list[dict[str, Any]],
    *,
    detector_column: str = "Idetname",
    columns: list[str] | None = None,
):
    dataframe = make_dataframe(rows)

    result = detector_filter_cut_rdataframe(
        dataframe,
        detectors,
        cut_filters,
        detector_column=detector_column,
    )

    if columns is None:
        columns = list(rows[0])

    actual = materialize(result, columns)

    assert actual == expected, (
        "\n"
        f"Detectors:\n{detectors}\n\n"
        f"Cuts:\n{cut_filters}\n\n"
        f"Expected:\n{expected}\n\n"
        f"Actual:\n{actual}"
    )


def check_detector_filter_many(
    dataframe_rows: list[list[dict[str, Any]]],
    detectors: str | list[str],
    cut_filters: str | list[str],
    expected: list[list[dict[str, Any]]],
    *,
    detector_column: str = "Idetname",
    columns: list[str] | None = None,
):
    dataframes = [
        make_dataframe(rows)
        for rows in dataframe_rows
    ]

    result = detector_filter_cut_rdataframe(
        dataframes,
        detectors,
        cut_filters,
        detector_column=detector_column,
    )

    assert isinstance(result, list)
    assert len(result) == len(dataframes)

    for index, (rows, result_df, expected_rows) in enumerate(
        zip(dataframe_rows, result, expected),
        start=1,
    ):
        use_columns = columns or list(rows[0])
        actual = materialize(result_df, use_columns)

        assert actual == expected_rows, (
            "\n"
            f"Dataframe: {index}\n"
            f"Detectors:\n{detectors}\n\n"
            f"Cuts:\n{cut_filters}\n\n"
            f"Expected:\n{expected_rows}\n\n"
            f"Actual:\n{actual}"
        )


# ===========================================================================
# 1-30: scalar detector / scalar cut cases
# ===========================================================================


SCALAR_CASES = [
    (
        "single_detector_gt",
        [
            {"Idetname": "A", "X": 1},
            {"Idetname": "A", "X": 10},
            {"Idetname": "B", "X": -100},
        ],
        ["A"],
        ["X > 5"],
        [
            {"Idetname": "A", "X": 10},
            {"Idetname": "B", "X": -100},
        ],
    ),
    (
        "single_detector_ge_boundary",
        [
            {"Idetname": "A", "X": 4},
            {"Idetname": "A", "X": 5},
            {"Idetname": "A", "X": 6},
            {"Idetname": "B", "X": 0},
        ],
        ["A"],
        ["X >= 5"],
        [
            {"Idetname": "A", "X": 5},
            {"Idetname": "A", "X": 6},
            {"Idetname": "B", "X": 0},
        ],
    ),
    (
        "single_detector_lt",
        [
            {"Idetname": "A", "X": -2},
            {"Idetname": "A", "X": 0},
            {"Idetname": "B", "X": 999},
        ],
        "A",
        "X < 0",
        [
            {"Idetname": "A", "X": -2},
            {"Idetname": "B", "X": 999},
        ],
    ),
    (
        "single_detector_equal",
        [
            {"Idetname": "A", "X": 3},
            {"Idetname": "A", "X": 4},
            {"Idetname": "C", "X": 4},
        ],
        "A",
        "X == 3",
        [
            {"Idetname": "A", "X": 3},
            {"Idetname": "C", "X": 4},
        ],
    ),
    (
        "single_detector_not_equal",
        [
            {"Idetname": "A", "X": 3},
            {"Idetname": "A", "X": 4},
            {"Idetname": "B", "X": 3},
        ],
        "A",
        "X != 3",
        [
            {"Idetname": "A", "X": 4},
            {"Idetname": "B", "X": 3},
        ],
    ),
    (
        "two_detectors_independent_thresholds",
        [
            {"Idetname": "A", "X": 5},
            {"Idetname": "A", "X": 15},
            {"Idetname": "B", "X": 15},
            {"Idetname": "B", "X": 25},
            {"Idetname": "C", "X": -1},
        ],
        ["A", "B"],
        ["X > 10", "X > 20"],
        [
            {"Idetname": "A", "X": 15},
            {"Idetname": "B", "X": 25},
            {"Idetname": "C", "X": -1},
        ],
    ),
    (
        "three_detectors_independent",
        [
            {"Idetname": "A", "X": 2},
            {"Idetname": "A", "X": 3},
            {"Idetname": "B", "X": 8},
            {"Idetname": "B", "X": 9},
            {"Idetname": "C", "X": 14},
            {"Idetname": "C", "X": 15},
            {"Idetname": "D", "X": -999},
        ],
        ["A", "B", "C"],
        ["X >= 3", "X >= 9", "X >= 15"],
        [
            {"Idetname": "A", "X": 3},
            {"Idetname": "B", "X": 9},
            {"Idetname": "C", "X": 15},
            {"Idetname": "D", "X": -999},
        ],
    ),
    (
        "unlisted_detectors_always_untouched",
        [
            {"Idetname": "A", "X": 0},
            {"Idetname": "B", "X": -100},
            {"Idetname": "C", "X": -200},
            {"Idetname": "D", "X": -300},
        ],
        ["A"],
        ["X > 1000"],
        [
            {"Idetname": "B", "X": -100},
            {"Idetname": "C", "X": -200},
            {"Idetname": "D", "X": -300},
        ],
    ),
    (
        "boolean_cut",
        [
            {"Idetname": "A", "Good": True, "X": 1},
            {"Idetname": "A", "Good": False, "X": 2},
            {"Idetname": "B", "Good": False, "X": 3},
        ],
        "A",
        "Good",
        [
            {"Idetname": "A", "Good": True, "X": 1},
            {"Idetname": "B", "Good": False, "X": 3},
        ],
    ),
    (
        "boolean_negation",
        [
            {"Idetname": "A", "Bad": True, "X": 1},
            {"Idetname": "A", "Bad": False, "X": 2},
            {"Idetname": "B", "Bad": True, "X": 3},
        ],
        "A",
        "!Bad",
        [
            {"Idetname": "A", "Bad": False, "X": 2},
            {"Idetname": "B", "Bad": True, "X": 3},
        ],
    ),
    (
        "and_cut",
        [
            {"Idetname": "A", "X": 5, "Y": 10},
            {"Idetname": "A", "X": 6, "Y": 10},
            {"Idetname": "A", "X": 7, "Y": 20},
            {"Idetname": "B", "X": 0, "Y": 0},
        ],
        "A",
        "X > 5 && Y < 15",
        [
            {"Idetname": "A", "X": 6, "Y": 10},
            {"Idetname": "B", "X": 0, "Y": 0},
        ],
    ),
    (
        "or_cut",
        [
            {"Idetname": "A", "X": 1, "Y": 0},
            {"Idetname": "A", "X": 0, "Y": 2},
            {"Idetname": "A", "X": 0, "Y": 0},
            {"Idetname": "B", "X": 0, "Y": 0},
        ],
        "A",
        "X == 1 || Y == 2",
        [
            {"Idetname": "A", "X": 1, "Y": 0},
            {"Idetname": "A", "X": 0, "Y": 2},
            {"Idetname": "B", "X": 0, "Y": 0},
        ],
    ),
    (
        "nested_boolean_cut",
        [
            {"Idetname": "A", "X": 5, "Y": 1, "Good": True},
            {"Idetname": "A", "X": 5, "Y": 9, "Good": False},
            {"Idetname": "A", "X": 1, "Y": 1, "Good": False},
            {"Idetname": "B", "X": 1, "Y": 1, "Good": False},
        ],
        "A",
        "(X >= 5 && (Y < 3 || Good)) || (X == 1 && Good)",
        [
            {"Idetname": "A", "X": 5, "Y": 1, "Good": True},
            {"Idetname": "B", "X": 1, "Y": 1, "Good": False},
        ],
    ),
    (
        "arithmetic_cut",
        [
            {"Idetname": "A", "X": 2, "Y": 3},
            {"Idetname": "A", "X": 4, "Y": 3},
            {"Idetname": "B", "X": -10, "Y": -10},
        ],
        "A",
        "X * 2 + Y >= 10",
        [
            {"Idetname": "A", "X": 4, "Y": 3},
            {"Idetname": "B", "X": -10, "Y": -10},
        ],
    ),
    (
        "floating_point_boundary",
        [
            {"Idetname": "A", "X": 0.499},
            {"Idetname": "A", "X": 0.5},
            {"Idetname": "A", "X": 0.501},
            {"Idetname": "B", "X": -4.0},
        ],
        "A",
        "X >= 0.5 && X < 0.501",
        [
            {"Idetname": "A", "X": 0.5},
            {"Idetname": "B", "X": -4.0},
        ],
    ),
    (
        "negative_numbers",
        [
            {"Idetname": "A", "X": -10},
            {"Idetname": "A", "X": -3},
            {"Idetname": "A", "X": 0},
            {"Idetname": "B", "X": -999},
        ],
        "A",
        "X >= -3",
        [
            {"Idetname": "A", "X": -3},
            {"Idetname": "A", "X": 0},
            {"Idetname": "B", "X": -999},
        ],
    ),
    (
        "scalar_string_cut",
        [
            {"Idetname": "A", "Particle": "muon", "X": 1},
            {"Idetname": "A", "Particle": "electron", "X": 2},
            {"Idetname": "B", "Particle": "electron", "X": 3},
        ],
        "A",
        'Particle == "muon"',
        [
            {"Idetname": "A", "Particle": "muon", "X": 1},
            {"Idetname": "B", "Particle": "electron", "X": 3},
        ],
    ),
    (
        "scalar_string_not_equal",
        [
            {"Idetname": "A", "Particle": "noise", "X": 1},
            {"Idetname": "A", "Particle": "muon", "X": 2},
            {"Idetname": "B", "Particle": "noise", "X": 3},
        ],
        "A",
        'Particle != "noise"',
        [
            {"Idetname": "A", "Particle": "muon", "X": 2},
            {"Idetname": "B", "Particle": "noise", "X": 3},
        ],
    ),
    (
        "two_detector_different_columns",
        [
            {"Idetname": "A", "X": 6, "Y": 0},
            {"Idetname": "A", "X": 4, "Y": 999},
            {"Idetname": "B", "X": 0, "Y": 9},
            {"Idetname": "B", "X": 999, "Y": 11},
            {"Idetname": "C", "X": 0, "Y": 0},
        ],
        ["A", "B"],
        ["X > 5", "Y > 10"],
        [
            {"Idetname": "A", "X": 6, "Y": 0},
            {"Idetname": "B", "X": 999, "Y": 11},
            {"Idetname": "C", "X": 0, "Y": 0},
        ],
    ),
    (
        "two_detector_bool_and_numeric",
        [
            {"Idetname": "A", "Good": True, "X": 5},
            {"Idetname": "A", "Good": False, "X": 50},
            {"Idetname": "B", "Good": False, "X": 20},
            {"Idetname": "B", "Good": True, "X": 1},
            {"Idetname": "C", "Good": False, "X": -1},
        ],
        ["A", "B"],
        ["Good && X >= 5", "!Good && X >= 10"],
        [
            {"Idetname": "A", "Good": True, "X": 5},
            {"Idetname": "B", "Good": False, "X": 20},
            {"Idetname": "C", "Good": False, "X": -1},
        ],
    ),
    (
        "same_numeric_values_different_detector_behavior",
        [
            {"Idetname": "A", "X": 10},
            {"Idetname": "B", "X": 10},
            {"Idetname": "C", "X": 10},
        ],
        ["A", "B"],
        ["X > 20", "X < 20"],
        [
            {"Idetname": "B", "X": 10},
            {"Idetname": "C", "X": 10},
        ],
    ),
    (
        "detector_order_irrelevant_semantics",
        [
            {"Idetname": "A", "X": 5},
            {"Idetname": "B", "X": 5},
            {"Idetname": "C", "X": 5},
        ],
        ["B", "A"],
        ["X > 10", "X < 10"],
        [
            {"Idetname": "A", "X": 5},
            {"Idetname": "C", "X": 5},
        ],
    ),
    (
        "four_detectors",
        [
            {"Idetname": "A", "X": 1},
            {"Idetname": "B", "X": 2},
            {"Idetname": "C", "X": 3},
            {"Idetname": "D", "X": 4},
            {"Idetname": "E", "X": -100},
        ],
        ["A", "B", "C", "D"],
        ["X == 1", "X > 10", "X == 3", "X < 0"],
        [
            {"Idetname": "A", "X": 1},
            {"Idetname": "C", "X": 3},
            {"Idetname": "E", "X": -100},
        ],
    ),
    (
        "all_target_detector_rows_fail",
        [
            {"Idetname": "A", "X": 1},
            {"Idetname": "A", "X": 2},
            {"Idetname": "B", "X": 3},
        ],
        "A",
        "X > 100",
        [
            {"Idetname": "B", "X": 3},
        ],
    ),
    (
        "all_target_detector_rows_pass",
        [
            {"Idetname": "A", "X": 1},
            {"Idetname": "A", "X": 2},
            {"Idetname": "B", "X": -999},
        ],
        "A",
        "X > 0",
        [
            {"Idetname": "A", "X": 1},
            {"Idetname": "A", "X": 2},
            {"Idetname": "B", "X": -999},
        ],
    ),
    (
        "no_rows_for_requested_detector",
        [
            {"Idetname": "B", "X": 1},
            {"Idetname": "C", "X": 2},
        ],
        "A",
        "X > 100000",
        [
            {"Idetname": "B", "X": 1},
            {"Idetname": "C", "X": 2},
        ],
    ),
    (
        "case_sensitive_detector_names",
        [
            {"Idetname": "Muon", "X": 0},
            {"Idetname": "muon", "X": 0},
            {"Idetname": "MUON", "X": 0},
        ],
        "Muon",
        "X > 1",
        [
            {"Idetname": "muon", "X": 0},
            {"Idetname": "MUON", "X": 0},
        ],
    ),
    (
        "detector_name_with_space",
        [
            {"Idetname": "Muon Entrance", "X": 1},
            {"Idetname": "Muon Entrance", "X": 2},
            {"Idetname": "Other", "X": 0},
        ],
        "Muon Entrance",
        "X == 2",
        [
            {"Idetname": "Muon Entrance", "X": 2},
            {"Idetname": "Other", "X": 0},
        ],
    ),
    (
        "detector_name_with_quote",
        [
            {"Idetname": 'Det"One', "X": 1},
            {"Idetname": 'Det"One', "X": 2},
            {"Idetname": "Other", "X": 0},
        ],
        'Det"One',
        "X == 2",
        [
            {"Idetname": 'Det"One', "X": 2},
            {"Idetname": "Other", "X": 0},
        ],
    ),
    (
        "detector_name_with_backslash",
        [
            {"Idetname": r"Det\One", "X": 1},
            {"Idetname": r"Det\One", "X": 2},
            {"Idetname": "Other", "X": 0},
        ],
        r"Det\One",
        "X == 1",
        [
            {"Idetname": r"Det\One", "X": 1},
            {"Idetname": "Other", "X": 0},
        ],
    ),
]


# ===========================================================================
# 31-70: vector-heavy detector-specific filtering
# ===========================================================================


VECTOR_CASES = [
    (
        "vector_numeric_basic",
        [{"Idetname": "A", "E": [10, 50, 100], "T": [1, 2, 3]}],
        "A",
        "E > 40",
        [{"Idetname": "A", "E": [50, 100], "T": [2, 3]}],
    ),
    (
        "vector_numeric_unlisted_detector_untouched",
        [{"Idetname": "B", "E": [1, 2, 3], "T": [4, 5, 6]}],
        "A",
        "E > 100",
        [{"Idetname": "B", "E": [1, 2, 3], "T": [4, 5, 6]}],
    ),
    (
        "vector_two_rows_target_and_other",
        [
            {"Idetname": "A", "E": [1, 5, 9], "T": [10, 20, 30]},
            {"Idetname": "B", "E": [0, 0], "T": [100, 200]},
        ],
        "A",
        "E >= 5",
        [
            {"Idetname": "A", "E": [5, 9], "T": [20, 30]},
            {"Idetname": "B", "E": [0, 0], "T": [100, 200]},
        ],
    ),
    (
        "vector_no_element_target_row_rejected",
        [
            {"Idetname": "A", "E": [1, 2], "T": [3, 4]},
            {"Idetname": "B", "E": [0], "T": [5]},
        ],
        "A",
        "E > 10",
        [
            {"Idetname": "B", "E": [0], "T": [5]},
        ],
    ),
    (
        "vector_all_elements_target_kept",
        [
            {"Idetname": "A", "E": [11, 12], "T": [3, 4]},
            {"Idetname": "B", "E": [0], "T": [5]},
        ],
        "A",
        "E > 10",
        [
            {"Idetname": "A", "E": [11, 12], "T": [3, 4]},
            {"Idetname": "B", "E": [0], "T": [5]},
        ],
    ),
    (
        "vector_two_conditions",
        [{"Idetname": "A", "E": [10, 50, 100, 200], "T": [1, 9, 3, 2]}],
        "A",
        "E >= 50 && T < 5",
        [{"Idetname": "A", "E": [100, 200], "T": [3, 2]}],
    ),
    (
        "vector_or_condition",
        [{"Idetname": "A", "E": [10, 50, 100, 200], "T": [9, 9, 3, 9]}],
        "A",
        "E >= 150 || T < 5",
        [{"Idetname": "A", "E": [100, 200], "T": [3, 9]}],
    ),
    (
        "vector_nested_condition",
        [{"Idetname": "A", "E": [10, 50, 100, 200], "T": [1, 9, 3, 2], "Good": [False, True, False, True]}],
        "A",
        "(E >= 100 && T < 5) || (Good && E < 100)",
        [{"Idetname": "A", "E": [50, 100, 200], "T": [9, 3, 2], "Good": [True, False, True]}],
    ),
    (
        "vector_bool_direct",
        [{"Idetname": "A", "X": [1, 2, 3, 4], "Good": [True, False, True, False]}],
        "A",
        "Good",
        [{"Idetname": "A", "X": [1, 3], "Good": [True, True]}],
    ),
    (
        "vector_bool_negated",
        [{"Idetname": "A", "X": [1, 2, 3, 4], "Bad": [True, False, True, False]}],
        "A",
        "!Bad",
        [{"Idetname": "A", "X": [2, 4], "Bad": [False, False]}],
    ),
    (
        "vector_bool_numeric",
        [{"Idetname": "A", "E": [20, 60, 100, 180], "Good": [True, True, False, True], "T": [1, 2, 3, 4]}],
        "A",
        "Good && E >= 50 && E < 200",
        [{"Idetname": "A", "E": [60, 180], "Good": [True, True], "T": [2, 4]}],
    ),
    (
        "vector_arithmetic",
        [{"Idetname": "A", "X": [1, 2, 3], "Y": [4, 5, 6]}],
        "A",
        "X + Y >= 8",
        [{"Idetname": "A", "X": [3], "Y": [6]}],
    ),
    (
        "vector_cross_multiply",
        [{"Idetname": "A", "X": [1, 2, 4], "Y": [5, 3, 2]}],
        "A",
        "X * Y > 6",
        [{"Idetname": "A", "X": [4], "Y": [2]}],
    ),
    (
        "vector_negative_values",
        [{"Idetname": "A", "X": [-3, -1, 0, 2], "Y": [1, 2, 3, 4]}],
        "A",
        "X < 0 && Y >= 2",
        [{"Idetname": "A", "X": [-1], "Y": [2]}],
    ),
    (
        "vector_double",
        [{"Idetname": "A", "X": [1.1, 2.2, 3.3], "Y": [0.5, 2.5, 4.5]}],
        "A",
        "X > 2.0 && Y < 4.0",
        [{"Idetname": "A", "X": [2.2], "Y": [2.5]}],
    ),
    (
        "vector_string_equal",
        [{"Idetname": "A", "Name": ["muon", "electron", "muon"], "E": [10, 20, 30]}],
        "A",
        'Name == "muon"',
        [{"Idetname": "A", "Name": ["muon", "muon"], "E": [10, 30]}],
    ),
    (
        "vector_string_not_equal",
        [{"Idetname": "A", "Name": ["noise", "muon", "noise", "proton"], "E": [1, 2, 3, 4]}],
        "A",
        'Name != "noise"',
        [{"Idetname": "A", "Name": ["muon", "proton"], "E": [2, 4]}],
    ),
    (
        "vector_string_numeric",
        [{"Idetname": "A", "Name": ["muon", "muon", "electron", "muon"], "E": [20, 80, 500, 150]}],
        "A",
        'Name == "muon" && E >= 50 && E < 200',
        [{"Idetname": "A", "Name": ["muon", "muon"], "E": [80, 150]}],
    ),
    (
        "vector_string_bool_numeric",
        [{"Idetname": "A", "Name": ["muon", "muon", "proton", "muon"], "Good": [True, False, True, True], "E": [60, 100, 300, 200]}],
        "A",
        'Name == "muon" && Good && E < 200',
        [{"Idetname": "A", "Name": ["muon"], "Good": [True], "E": [60]}],
    ),
    (
        "two_detector_vector_different_thresholds",
        [
            {"Idetname": "A", "E": [5, 15, 25], "T": [1, 2, 3]},
            {"Idetname": "B", "E": [5, 15, 25], "T": [4, 5, 6]},
            {"Idetname": "C", "E": [0, 0], "T": [7, 8]},
        ],
        ["A", "B"],
        ["E >= 15", "E >= 25"],
        [
            {"Idetname": "A", "E": [15, 25], "T": [2, 3]},
            {"Idetname": "B", "E": [25], "T": [6]},
            {"Idetname": "C", "E": [0, 0], "T": [7, 8]},
        ],
    ),
    (
        "two_detector_vector_different_columns",
        [
            {"Idetname": "A", "E": [1, 10, 20], "T": [9, 9, 9]},
            {"Idetname": "B", "E": [0, 0, 0], "T": [1, 5, 10]},
        ],
        ["A", "B"],
        ["E >= 10", "T < 6"],
        [
            {"Idetname": "A", "E": [10, 20], "T": [9, 9]},
            {"Idetname": "B", "E": [0, 0], "T": [1, 5]},
        ],
    ),
    (
        "three_detector_vector_logic",
        [
            {"Idetname": "A", "X": [1, 2, 3], "Y": [9, 8, 7]},
            {"Idetname": "B", "X": [1, 2, 3], "Y": [9, 8, 7]},
            {"Idetname": "C", "X": [1, 2, 3], "Y": [9, 8, 7]},
        ],
        ["A", "B", "C"],
        ["X >= 2", "Y <= 8", "X + Y == 10"],
        [
            {"Idetname": "A", "X": [2, 3], "Y": [8, 7]},
            {"Idetname": "B", "X": [2, 3], "Y": [8, 7]},
            {"Idetname": "C", "X": [1, 2, 3], "Y": [9, 8, 7]},
        ],
    ),
    (
        "scalar_gate_inside_vector_cut",
        [
            {"Idetname": "A", "Enabled": True, "E": [1, 10, 20]},
            {"Idetname": "A", "Enabled": False, "E": [100, 200]},
            {"Idetname": "B", "Enabled": False, "E": [0, 0]},
        ],
        "A",
        "Enabled && E >= 10",
        [
            {"Idetname": "A", "Enabled": True, "E": [10, 20]},
            {"Idetname": "B", "Enabled": False, "E": [0, 0]},
        ],
    ),
    (
        "scalar_threshold_inside_vector_cut",
        [
            {"Idetname": "A", "Threshold": 5, "E": [1, 5, 6]},
            {"Idetname": "A", "Threshold": 10, "E": [9, 10, 11]},
            {"Idetname": "B", "Threshold": 999, "E": [0]},
        ],
        "A",
        "E > Threshold",
        [
            {"Idetname": "A", "Threshold": 5, "E": [6]},
            {"Idetname": "A", "Threshold": 10, "E": [11]},
            {"Idetname": "B", "Threshold": 999, "E": [0]},
        ],
    ),
    (
        "scalar_range_inside_vector_cut",
        [
            {"Idetname": "A", "Low": 2, "High": 8, "E": [1, 3, 7, 9]},
            {"Idetname": "B", "Low": 999, "High": 1000, "E": [0, 1]},
        ],
        "A",
        "E > Low && E < High",
        [
            {"Idetname": "A", "Low": 2, "High": 8, "E": [3, 7]},
            {"Idetname": "B", "Low": 999, "High": 1000, "E": [0, 1]},
        ],
    ),
    (
        "four_aligned_vectors",
        [{"Idetname": "A", "A": [1, 2, 3], "B": [4, 5, 6], "C": [7, 8, 9], "D": [10, 11, 12]}],
        "A",
        "B >= 5 && D < 12",
        [{"Idetname": "A", "A": [2], "B": [5], "C": [8], "D": [11]}],
    ),
    (
        "column_name_prefixes",
        [{"Idetname": "A", "E": [1, 2, 3], "Energy": [4, 5, 6], "EnergyRaw": [7, 1, 9]}],
        "A",
        "Energy > 4 && EnergyRaw > 5",
        [{"Idetname": "A", "E": [3], "Energy": [6], "EnergyRaw": [9]}],
    ),
    (
        "vector_complex_boolean",
        [{"Idetname": "A", "X": [1, 2, 3, 4], "Y": [2, 8, 4, 9], "Z": [7, 1, 5, 3]}],
        "A",
        "(X <= 2 && Y >= 8) || (X > 2 && Z <= 3)",
        [{"Idetname": "A", "X": [2, 4], "Y": [8, 9], "Z": [1, 3]}],
    ),
    (
        "vector_nested_string_or",
        [{"Idetname": "A", "Name": ["electron", "muon", "proton", "gamma", "muon"], "E": [150, 20, 300, 1000, 90], "Good": [False, True, True, True, True]}],
        "A",
        '(Name == "muon" && Good) || (Name == "proton" && E > 200) || (Name == "electron" && !Good)',
        [{"Idetname": "A", "Name": ["electron", "muon", "proton", "muon"], "E": [150, 20, 300, 90], "Good": [False, True, True, True]}],
    ),
    (
        "vector_two_bool_vectors",
        [{"Idetname": "A", "A": [True, False, True, False], "B": [False, True, True, False], "X": [1, 2, 3, 4]}],
        "A",
        "(A && B) || (!A && !B)",
        [{"Idetname": "A", "A": [True, False], "B": [True, False], "X": [3, 4]}],
    ),
    (
        "vector_modulo",
        [{"Idetname": "A", "X": [1, 2, 3, 4, 5, 6], "Y": [10, 20, 30, 40, 50, 60]}],
        "A",
        "X % 2 == 0",
        [{"Idetname": "A", "X": [2, 4, 6], "Y": [20, 40, 60]}],
    ),
    (
        "vector_exact_float_values",
        [{"Idetname": "A", "X": [0.1, 0.5, 1.0, 1.5], "Y": [1, 2, 3, 4]}],
        "A",
        "X >= 0.5 && X <= 1.0",
        [{"Idetname": "A", "X": [0.5, 1.0], "Y": [2, 3]}],
    ),
    (
        "vector_unlisted_detector_complex_cut_untouched",
        [{"Idetname": "Z", "Name": ["noise", "noise"], "Good": [False, False], "E": [-1, -2]}],
        ["A", "B"],
        ['Name == "muon" && Good', "E > 1000"],
        [{"Idetname": "Z", "Name": ["noise", "noise"], "Good": [False, False], "E": [-1, -2]}],
    ),
    (
        "two_target_rows_different_masks",
        [
            {"Idetname": "A", "E": [1, 5, 7], "T": [10, 20, 30]},
            {"Idetname": "A", "E": [8, 1, 9], "T": [40, 50, 60]},
        ],
        "A",
        "E > 4",
        [
            {"Idetname": "A", "E": [5, 7], "T": [20, 30]},
            {"Idetname": "A", "E": [8, 9], "T": [40, 60]},
        ],
    ),
    (
        "one_target_row_rejected_one_survives",
        [
            {"Idetname": "A", "E": [1, 2], "T": [10, 20]},
            {"Idetname": "A", "E": [8, 9], "T": [30, 40]},
            {"Idetname": "B", "E": [0], "T": [50]},
        ],
        "A",
        "E > 5",
        [
            {"Idetname": "A", "E": [8, 9], "T": [30, 40]},
            {"Idetname": "B", "E": [0], "T": [50]},
        ],
    ),
    (
        "different_detector_vector_types_same_call",
        [
            {"Idetname": "A", "Name": ["muon", "electron"], "E": [10, 20]},
            {"Idetname": "B", "Name": ["noise", "noise"], "E": [50, 100]},
        ],
        ["A", "B"],
        ['Name == "muon"', "E >= 100"],
        [
            {"Idetname": "A", "Name": ["muon"], "E": [10]},
            {"Idetname": "B", "Name": ["noise"], "E": [100]},
        ],
    ),
    (
        "five_detectors_vectors",
        [
            {"Idetname": "A", "X": [1, 2, 3]},
            {"Idetname": "B", "X": [1, 2, 3]},
            {"Idetname": "C", "X": [1, 2, 3]},
            {"Idetname": "D", "X": [1, 2, 3]},
            {"Idetname": "E", "X": [1, 2, 3]},
            {"Idetname": "F", "X": [0]},
        ],
        ["A", "B", "C", "D", "E"],
        ["X == 1", "X == 2", "X == 3", "X <= 2", "X >= 2"],
        [
            {"Idetname": "A", "X": [1]},
            {"Idetname": "B", "X": [2]},
            {"Idetname": "C", "X": [3]},
            {"Idetname": "D", "X": [1, 2]},
            {"Idetname": "E", "X": [2, 3]},
            {"Idetname": "F", "X": [0]},
        ],
    ),
    (
        "vector_scalar_force_or",
        [
            {"Idetname": "A", "Force": True, "X": [1, 2, 3], "E": [0, 0, 0]},
            {"Idetname": "A", "Force": False, "X": [4, 5, 6], "E": [0, 10, 0]},
        ],
        "A",
        "Force || E > 5",
        [
            {"Idetname": "A", "Force": True, "X": [1, 2, 3], "E": [0, 0, 0]},
            {"Idetname": "A", "Force": False, "X": [5], "E": [10]},
        ],
    ),
    (
        "vector_deep_parentheses",
        [{"Idetname": "A", "X": [1, 2, 3, 4, 5], "Y": [5, 4, 3, 2, 1], "G": [True, False, True, False, True]}],
        "A",
        "((X >= 2 && Y <= 4) && (G || X == 4)) || (X == 5 && Y == 1)",
        [{"Idetname": "A", "X": [3, 4, 5], "Y": [3, 2, 1], "G": [True, False, True]}],
    ),
    (
        "vector_string_three_targets",
        [{"Idetname": "A", "Name": ["muon", "electron", "proton", "gamma", "kaon"], "E": [1, 2, 3, 4, 5]}],
        "A",
        'Name == "muon" || Name == "proton" || Name == "kaon"',
        [{"Idetname": "A", "Name": ["muon", "proton", "kaon"], "E": [1, 3, 5]}],
    ),
]


# ===========================================================================
# 71-82: Char_t detector names and custom detector-column cases
# ===========================================================================


def _char_expected(rows, indices, columns):
    result = []
    for index in indices:
        row = rows[index]
        result.append({
            column: (
                row[column].value
                if isinstance(row[column], CharArray)
                else row[column]
            )
            for column in columns
        })
    return result


def test_char_detector_scalar_cut():
    rows = [
        {"Idetname": CharArray("A"), "X": 1},
        {"Idetname": CharArray("A"), "X": 10},
        {"Idetname": CharArray("B"), "X": -1},
    ]
    dataframe = make_dataframe(rows)
    result = detector_filter_cut_rdataframe(
        dataframe,
        "A",
        "X > 5",
        "Idetname"
    )
    assert materialize(result, ["X"]) == [
        {"X": 10},
        {"X": -1},
    ]


def test_char_detector_two_detectors():
    rows = [
        {"Idetname": CharArray("A"), "X": 5},
        {"Idetname": CharArray("A"), "X": 15},
        {"Idetname": CharArray("B"), "X": 15},
        {"Idetname": CharArray("B"), "X": 25},
        {"Idetname": CharArray("C"), "X": -100},
    ]
    dataframe = make_dataframe(rows)
    result = detector_filter_cut_rdataframe(
        dataframe,
        ["A", "B"],
        ["X > 10", "X > 20"],
        "Idetname"
    )
    assert materialize(result, ["X"]) == [
        {"X": 15},
        {"X": 25},
        {"X": -100},
    ]


def test_char_detector_vector_cut():
    rows = [
        {"Idetname": CharArray("A"), "E": [1, 5, 9], "T": [10, 20, 30]},
        {"Idetname": CharArray("B"), "E": [0, 0], "T": [40, 50]},
    ]
    dataframe = make_dataframe(rows)
    result = detector_filter_cut_rdataframe(
        dataframe,
        "A",
        "E >= 5",
        "Idetname"
    )
    assert materialize(result, ["E", "T"]) == [
        {"E": [5, 9], "T": [20, 30]},
        {"E": [0, 0], "T": [40, 50]},
    ]


def test_char_detector_string_vector_cut():
    rows = [
        {"Idetname": CharArray("A"), "Name": ["muon", "electron", "muon"], "E": [1, 2, 3]},
        {"Idetname": CharArray("B"), "Name": ["noise"], "E": [99]},
    ]
    dataframe = make_dataframe(rows)
    result = detector_filter_cut_rdataframe(
        dataframe,
        "A",
        'Name == "muon"',
        "Idetname"
    )
    assert materialize(result, ["Name", "E"]) == [
        {"Name": ["muon", "muon"], "E": [1, 3]},
        {"Name": ["noise"], "E": [99]},
    ]


def test_custom_detector_column_scalar():
    check_detector_filter(
        [
            {"Detector": "A", "X": 1},
            {"Detector": "A", "X": 2},
            {"Detector": "B", "X": 0},
        ],
        "A",
        "X == 2",
        [
            {"Detector": "A", "X": 2},
            {"Detector": "B", "X": 0},
        ],
        detector_column="Detector",
    )


def test_custom_detector_column_two_detectors():
    check_detector_filter(
        [
            {"DetectorName": "A", "X": 5},
            {"DetectorName": "B", "X": 5},
            {"DetectorName": "C", "X": 5},
        ],
        ["A", "B"],
        ["X > 10", "X < 10"],
        [
            {"DetectorName": "B", "X": 5},
            {"DetectorName": "C", "X": 5},
        ],
        detector_column="DetectorName",
    )


def test_custom_detector_column_vector():
    check_detector_filter(
        [
            {"Detector": "A", "X": [1, 2, 3], "Y": [10, 20, 30]},
            {"Detector": "B", "X": [0], "Y": [99]},
        ],
        "A",
        "X >= 2",
        [
            {"Detector": "A", "X": [2, 3], "Y": [20, 30]},
            {"Detector": "B", "X": [0], "Y": [99]},
        ],
        detector_column="Detector",
    )


def test_custom_char_detector_column():
    rows = [
        {"Detector": CharArray("A"), "X": 1},
        {"Detector": CharArray("A"), "X": 2},
        {"Detector": CharArray("B"), "X": 3},
    ]
    dataframe = make_dataframe(rows)
    result = detector_filter_cut_rdataframe(
        dataframe,
        "A",
        "X > 1",
        detector_column="Detector",
    )
    assert materialize(result, ["X"]) == [
        {"X": 2},
        {"X": 3},
    ]


def test_detector_name_underscore_digits():
    check_detector_filter(
        [
            {"Idetname": "Muon_Entrance_2", "X": 1},
            {"Idetname": "Muon_Entrance_2", "X": 2},
            {"Idetname": "Other", "X": 0},
        ],
        "Muon_Entrance_2",
        "X > 1",
        [
            {"Idetname": "Muon_Entrance_2", "X": 2},
            {"Idetname": "Other", "X": 0},
        ],
    )


def test_detector_name_parentheses_and_dash():
    check_detector_filter(
        [
            {"Idetname": "Det-(A)", "X": 1},
            {"Idetname": "Det-(A)", "X": 2},
            {"Idetname": "Other", "X": 0},
        ],
        "Det-(A)",
        "X == 1",
        [
            {"Idetname": "Det-(A)", "X": 1},
            {"Idetname": "Other", "X": 0},
        ],
    )


def test_char_detector_three_rules():
    rows = [
        {"Idetname": CharArray("A"), "X": 1},
        {"Idetname": CharArray("B"), "X": 2},
        {"Idetname": CharArray("C"), "X": 3},
        {"Idetname": CharArray("D"), "X": 0},
    ]
    dataframe = make_dataframe(rows)
    result = detector_filter_cut_rdataframe(
        dataframe,
        ["A", "B", "C"],
        ["X == 1", "X > 10", "X == 3"],
        "Idetname"
    )
    assert materialize(result, ["X"]) == [
        {"X": 1},
        {"X": 3},
        {"X": 0},
    ]


def test_char_detector_bool_vector():
    rows = [
        {"Idetname": CharArray("A"), "X": [1, 2, 3], "Good": [True, False, True]},
        {"Idetname": CharArray("B"), "X": [9], "Good": [False]},
    ]
    dataframe = make_dataframe(rows)
    result = detector_filter_cut_rdataframe(
        dataframe,
        "A",
        "Good",
        "Idetname"
    )
    assert materialize(result, ["X", "Good"]) == [
        {"X": [1, 3], "Good": [True, True]},
        {"X": [9], "Good": [False]},
    ]


# ===========================================================================
# 83-94: multiple RDataFrames
# ===========================================================================


MULTI_CASES = [
    (
        "two_dataframes_scalar",
        [
            [
                {"Idetname": "A", "X": 1},
                {"Idetname": "A", "X": 5},
                {"Idetname": "B", "X": 0},
            ],
            [
                {"Idetname": "A", "X": 10},
                {"Idetname": "B", "X": -10},
            ],
        ],
        "A",
        "X >= 5",
        [
            [
                {"Idetname": "A", "X": 5},
                {"Idetname": "B", "X": 0},
            ],
            [
                {"Idetname": "A", "X": 10},
                {"Idetname": "B", "X": -10},
            ],
        ],
    ),
    (
        "three_dataframes_two_detectors",
        [
            [
                {"Idetname": "A", "X": 5},
                {"Idetname": "B", "X": 25},
            ],
            [
                {"Idetname": "A", "X": 15},
                {"Idetname": "B", "X": 15},
            ],
            [
                {"Idetname": "C", "X": -999},
                {"Idetname": "B", "X": 30},
            ],
        ],
        ["A", "B"],
        ["X > 10", "X > 20"],
        [
            [
                {"Idetname": "B", "X": 25},
            ],
            [
                {"Idetname": "A", "X": 15},
            ],
            [
                {"Idetname": "C", "X": -999},
                {"Idetname": "B", "X": 30},
            ],
        ],
    ),
    (
        "two_dataframes_vectors",
        [
            [{"Idetname": "A", "E": [1, 5, 9], "T": [1, 2, 3]}],
            [{"Idetname": "A", "E": [10, 2, 20], "T": [4, 5, 6]}],
        ],
        "A",
        "E >= 5",
        [
            [{"Idetname": "A", "E": [5, 9], "T": [2, 3]}],
            [{"Idetname": "A", "E": [10, 20], "T": [4, 6]}],
        ],
    ),
    (
        "two_dataframes_target_and_unlisted",
        [
            [{"Idetname": "A", "X": 0}],
            [{"Idetname": "Z", "X": -999}],
        ],
        "A",
        "X > 100",
        [
            [],
            [{"Idetname": "Z", "X": -999}],
        ],
    ),
    (
        "three_dataframes_vector_different_detectors",
        [
            [{"Idetname": "A", "X": [1, 2, 3]}],
            [{"Idetname": "B", "X": [1, 2, 3]}],
            [{"Idetname": "C", "X": [1, 2, 3]}],
        ],
        ["A", "B"],
        ["X >= 2", "X <= 2"],
        [
            [{"Idetname": "A", "X": [2, 3]}],
            [{"Idetname": "B", "X": [1, 2]}],
            [{"Idetname": "C", "X": [1, 2, 3]}],
        ],
    ),
    (
        "four_dataframes_scalar_boundaries",
        [
            [{"Idetname": "A", "X": 4}, {"Idetname": "A", "X": 5}],
            [{"Idetname": "A", "X": 5}, {"Idetname": "A", "X": 6}],
            [{"Idetname": "B", "X": 0}],
            [{"Idetname": "C", "X": -1}],
        ],
        "A",
        "X >= 5",
        [
            [{"Idetname": "A", "X": 5}],
            [{"Idetname": "A", "X": 5}, {"Idetname": "A", "X": 6}],
            [{"Idetname": "B", "X": 0}],
            [{"Idetname": "C", "X": -1}],
        ],
    ),
    (
        "two_dataframes_string_vector",
        [
            [{"Idetname": "A", "Name": ["muon", "electron"], "E": [1, 2]}],
            [{"Idetname": "A", "Name": ["proton", "muon"], "E": [3, 4]}],
        ],
        "A",
        'Name == "muon"',
        [
            [{"Idetname": "A", "Name": ["muon"], "E": [1]}],
            [{"Idetname": "A", "Name": ["muon"], "E": [4]}],
        ],
    ),
    (
        "two_dataframes_mixed_scalar_vector",
        [
            [
                {"Idetname": "A", "Enabled": True, "E": [1, 10, 20]},
                {"Idetname": "B", "Enabled": False, "E": [0]},
            ],
            [
                {"Idetname": "A", "Enabled": False, "E": [100, 200]},
                {"Idetname": "C", "Enabled": False, "E": [0]},
            ],
        ],
        "A",
        "Enabled && E >= 10",
        [
            [
                {"Idetname": "A", "Enabled": True, "E": [10, 20]},
                {"Idetname": "B", "Enabled": False, "E": [0]},
            ],
            [
                {"Idetname": "C", "Enabled": False, "E": [0]},
            ],
        ],
    ),
    (
        "three_dataframes_three_detector_rules",
        [
            [{"Idetname": "A", "X": 1}, {"Idetname": "D", "X": 0}],
            [{"Idetname": "B", "X": 2}, {"Idetname": "D", "X": 0}],
            [{"Idetname": "C", "X": 3}, {"Idetname": "D", "X": 0}],
        ],
        ["A", "B", "C"],
        ["X == 1", "X > 10", "X == 3"],
        [
            [{"Idetname": "A", "X": 1}, {"Idetname": "D", "X": 0}],
            [{"Idetname": "D", "X": 0}],
            [{"Idetname": "C", "X": 3}, {"Idetname": "D", "X": 0}],
        ],
    ),
    (
        "two_dataframes_complex_boolean",
        [
            [
                {"Idetname": "A", "X": 5, "Y": 2, "Good": True},
                {"Idetname": "A", "X": 5, "Y": 9, "Good": False},
            ],
            [
                {"Idetname": "A", "X": 1, "Y": 1, "Good": True},
                {"Idetname": "B", "X": 0, "Y": 0, "Good": False},
            ],
        ],
        "A",
        "(X >= 5 && (Y < 3 || Good)) || (X == 1 && Good)",
        [
            [{"Idetname": "A", "X": 5, "Y": 2, "Good": True}],
            [
                {"Idetname": "A", "X": 1, "Y": 1, "Good": True},
                {"Idetname": "B", "X": 0, "Y": 0, "Good": False},
            ],
        ],
    ),
    (
        "two_dataframes_unlisted_only",
        [
            [{"Idetname": "X", "V": [1, 2]}],
            [{"Idetname": "Y", "V": [3, 4]}],
        ],
        ["A", "B"],
        ["V > 100", "V < -100"],
        [
            [{"Idetname": "X", "V": [1, 2]}],
            [{"Idetname": "Y", "V": [3, 4]}],
        ],
    ),
    (
        "five_dataframes_one_rule",
        [
            [{"Idetname": "A", "X": 1}],
            [{"Idetname": "A", "X": 2}],
            [{"Idetname": "A", "X": 3}],
            [{"Idetname": "B", "X": -1}],
            [{"Idetname": "C", "X": -2}],
        ],
        "A",
        "X >= 2",
        [
            [],
            [{"Idetname": "A", "X": 2}],
            [{"Idetname": "A", "X": 3}],
            [{"Idetname": "B", "X": -1}],
            [{"Idetname": "C", "X": -2}],
        ],
    ),
]


# ===========================================================================
# 95-100: API/shape/interaction black-box tests
# ===========================================================================


def test_single_dataframe_returns_single_dataframe():
    dataframe = make_dataframe([
        {"Idetname": "A", "X": 1},
        {"Idetname": "A", "X": 2},
    ])

    result = detector_filter_cut_rdataframe(
        dataframe,
        "A",
        "X > 1",
        "Idetname"
    )

    assert not isinstance(result, list)
    assert materialize(result, ["Idetname", "X"]) == [
        {"Idetname": "A", "X": 2},
    ]


def test_dataframe_list_returns_list():
    first = make_dataframe([
        {"Idetname": "A", "X": 1},
        {"Idetname": "B", "X": 2},
    ])
    second = make_dataframe([
        {"Idetname": "A", "X": 3},
        {"Idetname": "B", "X": 4},
    ])

    result = detector_filter_cut_rdataframe(
        [first, second],
        "A",
        "X >= 3",
        "Idetname"
    )

    assert isinstance(result, list)
    assert len(result) == 2
    assert materialize(result[0], ["Idetname", "X"]) == [
        {"Idetname": "B", "X": 2},
    ]
    assert materialize(result[1], ["Idetname", "X"]) == [
        {"Idetname": "A", "X": 3},
        {"Idetname": "B", "X": 4},
    ]


def test_tuple_dataframe_input_returns_list_like_existing_contract():
    first = make_dataframe([
        {"Idetname": "A", "X": 1},
        {"Idetname": "B", "X": 2},
    ])
    second = make_dataframe([
        {"Idetname": "A", "X": 5},
        {"Idetname": "C", "X": 6},
    ])

    result = detector_filter_cut_rdataframe(
        (first, second),
        "A",
        "X > 2",
        "Idetname"
    )

    assert isinstance(result, list)
    assert materialize(result[0], ["Idetname", "X"]) == [
        {"Idetname": "B", "X": 2},
    ]
    assert materialize(result[1], ["Idetname", "X"]) == [
        {"Idetname": "A", "X": 5},
        {"Idetname": "C", "X": 6},
    ]

def test_many_rules_one_row_each():
    rows = [
        {"Idetname": "D1", "X": 1},
        {"Idetname": "D2", "X": 2},
        {"Idetname": "D3", "X": 3},
        {"Idetname": "D4", "X": 4},
        {"Idetname": "D5", "X": 5},
        {"Idetname": "Other", "X": -100},
    ]

    check_detector_filter(
        rows,
        ["D1", "D2", "D3", "D4", "D5"],
        ["X == 1", "X > 10", "X == 3", "X < 4", "X >= 5"],
        [
            {"Idetname": "D1", "X": 1},
            {"Idetname": "D3", "X": 3},
            {"Idetname": "D5", "X": 5},
            {"Idetname": "Other", "X": -100},
        ],
    )


def test_multiple_rules_with_vector_and_scalar_rows():
    rows = [
        {"Idetname": "A", "Enabled": True, "E": [10, 60, 100], "T": [1, 2, 3]},
        {"Idetname": "B", "Enabled": False, "E": [10, 60, 100], "T": [4, 5, 6]},
        {"Idetname": "C", "Enabled": False, "E": [0, 0], "T": [7, 8]},
    ]

    check_detector_filter(
        rows,
        ["A", "B"],
        [
            "Enabled && E >= 50",
            "!Enabled && T >= 5",
        ],
        [
            {"Idetname": "A", "Enabled": True, "E": [60, 100], "T": [2, 3]},
            {"Idetname": "B", "Enabled": False, "E": [60, 100], "T": [5, 6]},
            {"Idetname": "C", "Enabled": False, "E": [0, 0], "T": [7, 8]},
        ],
    )


def test_large_combined_logic_known_output():
    rows = [
        {
            "Idetname": "Muon",
            "Mode": "Physics",
            "Particle": ["muon", "electron", "proton", "muon", "gamma", "proton"],
            "Good": [True, True, True, False, True, False],
            "Triggered": [False, True, True, True, True, True],
            "Energy": [60, 500, 300, 120, 1000, 600],
            "Time": [1, 2, 3, 4, 5, 6],
        },
        {
            "Idetname": "Tracker",
            "Mode": "Physics",
            "Particle": ["noise", "noise", "noise"],
            "Good": [False, False, False],
            "Triggered": [False, False, False],
            "Energy": [1, 2, 3],
            "Time": [10, 11, 12],
        },
    ]

    check_detector_filter(
        rows,
        "Muon",
        (
            'Mode == "Physics" && '
            '((Particle == "muon" && Good && Energy >= 50 && Energy < 200) '
            '|| (Particle == "proton" && Triggered && Energy >= 250)) '
            '&& Time <= 5'
        ),
        [
            {
                "Idetname": "Muon",
                "Mode": "Physics",
                "Particle": ["muon", "proton"],
                "Good": [True, True],
                "Triggered": [False, True],
                "Energy": [60, 300],
                "Time": [1, 3],
            },
            {
                "Idetname": "Tracker",
                "Mode": "Physics",
                "Particle": ["noise", "noise", "noise"],
                "Good": [False, False, False],
                "Triggered": [False, False, False],
                "Energy": [1, 2, 3],
                "Time": [10, 11, 12],
            },
        ],
    )


# ===========================================================================
# 101-150: adversarial / weird vector-expression regressions
# ===========================================================================
#
# These are intentionally concentrated around combinations that are easy for
# ROOT's JIT / RVec<bool> expression handling to get wrong:
#   - multiple RVec<bool> operands
#   - nested negation and De Morgan forms
#   - scalar + vector boolean broadcasting
#   - string-vector + bool-vector expressions
#   - detector names colliding with column names / string literals
#   - identifier prefixes (A, AA, A1)
#   - multiple detectors with different vector masks
#   - applying one boolean mask to aligned vectors of several data types
#
# They use the same black-box contract as the existing suite.
# ===========================================================================

WEIRD_CASES = [('bool_xnor_two_vectors',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  'A',
  '(P && Q) || (!P && !Q)',
  [{'Idetname': 'A', 'P': [True, False], 'Q': [True, False], 'X': [1, 4]}]),
 ('bool_xor_two_vectors',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  'A',
  '(P && !Q) || (!P && Q)',
  [{'Idetname': 'A', 'P': [False, True], 'Q': [True, False], 'X': [2, 3]}]),
 ('bool_demorgan_not_and',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  'A',
  '!(P && Q)',
  [{'Idetname': 'A', 'P': [False, True, False], 'Q': [True, False, False], 'X': [2, 3, 4]}]),
 ('bool_demorgan_not_or',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  'A',
  '!(P || Q)',
  [{'Idetname': 'A', 'P': [False], 'Q': [False], 'X': [4]}]),
 ('bool_double_negation',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  'A',
  '!!P',
  [{'Idetname': 'A', 'P': [True, True], 'Q': [True, False], 'X': [1, 3]}]),
 ('bool_nested_negations',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  'A',
  '!(!P || Q)',
  [{'Idetname': 'A', 'P': [True], 'Q': [False], 'X': [3]}]),
 ('bool_equivalent_or_form',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  'A',
  '(P || !Q) && (!P || Q)',
  [{'Idetname': 'A', 'P': [True, False], 'Q': [True, False], 'X': [1, 4]}]),
 ('bool_three_term_logic',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  'A',
  '(P && Q) || (P && !Q) || (!P && !Q)',
  [{'Idetname': 'A', 'P': [True, True, False], 'Q': [True, False, False], 'X': [1, 3, 4]}]),
 ('bool_three_vectors_majority',
  [{'Idetname': 'A',
    'P': [True, True, False, False],
    'Q': [True, False, True, False],
    'R': [False, True, True, False],
    'X': [1, 2, 3, 4]}],
  'A',
  '(P && Q) || (P && R) || (Q && R)',
  [{'Idetname': 'A',
    'P': [True, True, False],
    'Q': [True, False, True],
    'R': [False, True, True],
    'X': [1, 2, 3]}]),
 ('bool_three_vectors_exactly_one',
  [{'Idetname': 'A',
    'P': [True, True, False, False],
    'Q': [True, False, True, False],
    'R': [False, True, True, False],
    'X': [1, 2, 3, 4]}],
  'A',
  '(P && !Q && !R) || (!P && Q && !R) || (!P && !Q && R)',
  []),
 ('bool_three_vectors_all_equal',
  [{'Idetname': 'A',
    'P': [True, True, False, False],
    'Q': [True, False, True, False],
    'R': [False, True, True, False],
    'X': [1, 2, 3, 4]}],
  'A',
  '(P && Q && R) || (!P && !Q && !R)',
  [{'Idetname': 'A', 'P': [False], 'Q': [False], 'R': [False], 'X': [4]}]),
 ('bool_three_vectors_mixed_parentheses',
  [{'Idetname': 'A',
    'P': [True, True, False, False],
    'Q': [True, False, True, False],
    'R': [False, True, True, False],
    'X': [1, 2, 3, 4]}],
  'A',
  '(P && (Q || R)) || (!P && !Q)',
  [{'Idetname': 'A',
    'P': [True, True, False],
    'Q': [True, False, False],
    'R': [False, True, False],
    'X': [1, 2, 4]}]),
 ('bool_negation_chain_with_or',
  [{'Idetname': 'A',
    'P': [True, True, False, False],
    'Q': [True, False, True, False],
    'R': [False, True, True, False],
    'X': [1, 2, 3, 4]}],
  'A',
  '(!P && Q) || (!Q && R)',
  [{'Idetname': 'A', 'P': [True, False], 'Q': [False, True], 'R': [True, True], 'X': [2, 3]}]),
 ('bool_same_column_reused',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  'A',
  '(P && P) || (!P && !P)',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}]),
 ('bool_tautology_from_vector',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  'A',
  'P || !P',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}]),
 ('bool_numeric_negated_branch',
  [{'Idetname': 'A', 'Good': [True, False, True, False], 'E': [0, 10, 20, 30], 'X': [1, 2, 3, 4]}],
  'A',
  '(Good && E >= 20) || (!Good && E >= 30)',
  [{'Idetname': 'A', 'Good': [True, False], 'E': [20, 30], 'X': [3, 4]}]),
 ('bool_numeric_xor_style',
  [{'Idetname': 'A', 'Good': [True, False, True, False], 'E': [0, 10, 20, 30], 'X': [1, 2, 3, 4]}],
  'A',
  '(Good && E < 15) || (!Good && E >= 15)',
  [{'Idetname': 'A', 'Good': [True, False], 'E': [0, 30], 'X': [1, 4]}]),
 ('bool_numeric_double_negation',
  [{'Idetname': 'A', 'Good': [True, False, True, False], 'E': [0, 10, 20, 30], 'X': [1, 2, 3, 4]}],
  'A',
  '!!Good && E >= 0',
  [{'Idetname': 'A', 'Good': [True, True], 'E': [0, 20], 'X': [1, 3]}]),
 ('bool_numeric_not_group',
  [{'Idetname': 'A', 'Good': [True, False, True, False], 'E': [0, 10, 20, 30], 'X': [1, 2, 3, 4]}],
  'A',
  '!(Good && E < 25)',
  [{'Idetname': 'A', 'Good': [False, False], 'E': [10, 30], 'X': [2, 4]}]),
 ('bool_numeric_nested_or',
  [{'Idetname': 'A', 'Good': [True, False, True, False], 'E': [0, 10, 20, 30], 'X': [1, 2, 3, 4]}],
  'A',
  '(Good && (E == 0 || E == 20)) || (!Good && E == 10)',
  [{'Idetname': 'A', 'Good': [True, False, True], 'E': [0, 10, 20], 'X': [1, 2, 3]}]),
 ('scalar_true_and_bool_vector',
  [{'Idetname': 'A', 'Enabled': True, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [10, 20, 30]},
   {'Idetname': 'A', 'Enabled': False, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [40, 50, 60]}],
  'A',
  'Enabled && Good',
  [{'Idetname': 'A', 'Enabled': True, 'Good': [True, True], 'E': [1, 10], 'X': [10, 30]}]),
 ('scalar_false_or_bool_vector',
  [{'Idetname': 'A', 'Enabled': True, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [10, 20, 30]},
   {'Idetname': 'A', 'Enabled': False, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [40, 50, 60]}],
  'A',
  '!Enabled || Good',
  [{'Idetname': 'A', 'Enabled': True, 'Good': [True, True], 'E': [1, 10], 'X': [10, 30]},
   {'Idetname': 'A', 'Enabled': False, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [40, 50, 60]}]),
 ('scalar_gate_compound_bool_vector',
  [{'Idetname': 'A', 'Enabled': True, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [10, 20, 30]},
   {'Idetname': 'A', 'Enabled': False, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [40, 50, 60]}],
  'A',
  '(Enabled && Good) || (!Enabled && !Good)',
  [{'Idetname': 'A', 'Enabled': True, 'Good': [True, True], 'E': [1, 10], 'X': [10, 30]},
   {'Idetname': 'A', 'Enabled': False, 'Good': [False], 'E': [5], 'X': [50]}]),
 ('scalar_numeric_bool_vector_mix',
  [{'Idetname': 'A', 'Enabled': True, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [10, 20, 30]},
   {'Idetname': 'A', 'Enabled': False, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [40, 50, 60]}],
  'A',
  '(Enabled && Good && E >= 5) || (!Enabled && E == 10)',
  [{'Idetname': 'A', 'Enabled': True, 'Good': [True], 'E': [10], 'X': [30]},
   {'Idetname': 'A', 'Enabled': False, 'Good': [True], 'E': [10], 'X': [60]}]),
 ('scalar_force_compound_bool',
  [{'Idetname': 'A', 'Enabled': True, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [10, 20, 30]},
   {'Idetname': 'A', 'Enabled': False, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [40, 50, 60]}],
  'A',
  'Enabled || (Good && E >= 10)',
  [{'Idetname': 'A', 'Enabled': True, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [10, 20, 30]},
   {'Idetname': 'A', 'Enabled': False, 'Good': [True], 'E': [10], 'X': [60]}]),
 ('bool_string_and',
  [{'Idetname': 'A', 'Flag': [True, False, True, False], 'Name': ['A', 'B', 'A', 'C'], 'X': [1, 2, 3, 4]}],
  'A',
  'Flag && Name == "A"',
  [{'Idetname': 'A', 'Flag': [True, True], 'Name': ['A', 'A'], 'X': [1, 3]}]),
 ('bool_string_negated_and',
  [{'Idetname': 'A', 'Flag': [True, False, True, False], 'Name': ['A', 'B', 'A', 'C'], 'X': [1, 2, 3, 4]}],
  'A',
  '!Flag && Name != "A"',
  [{'Idetname': 'A', 'Flag': [False, False], 'Name': ['B', 'C'], 'X': [2, 4]}]),
 ('bool_string_or',
  [{'Idetname': 'A', 'Flag': [True, False, True, False], 'Name': ['A', 'B', 'A', 'C'], 'X': [1, 2, 3, 4]}],
  'A',
  '(Flag && Name == "A") || (!Flag && Name == "C")',
  [{'Idetname': 'A', 'Flag': [True, True, False], 'Name': ['A', 'A', 'C'], 'X': [1, 3, 4]}]),
 ('bool_string_not_group',
  [{'Idetname': 'A', 'Flag': [True, False, True, False], 'Name': ['A', 'B', 'A', 'C'], 'X': [1, 2, 3, 4]}],
  'A',
  '!(Flag && Name == "A")',
  [{'Idetname': 'A', 'Flag': [False, False], 'Name': ['B', 'C'], 'X': [2, 4]}]),
 ('bool_string_multiple_literals',
  [{'Idetname': 'A', 'Flag': [True, False, True, False], 'Name': ['A', 'B', 'A', 'C'], 'X': [1, 2, 3, 4]}],
  'A',
  '(Name == "A" && Flag) || (Name == "B" && !Flag)',
  [{'Idetname': 'A', 'Flag': [True, False, True], 'Name': ['A', 'B', 'A'], 'X': [1, 2, 3]}]),
 ('bool_column_same_as_detector_and_literal',
  [{'Idetname': 'A', 'A': [True, False, True, False], 'Name': ['A', 'A', 'B', 'A'], 'X': [1, 2, 3, 4]}],
  'A',
  'A && Name == "A"',
  [{'Idetname': 'A', 'A': [True], 'Name': ['A'], 'X': [1]}]),
 ('bool_column_same_as_detector_negated_literal',
  [{'Idetname': 'A', 'A': [True, False, True, False], 'Name': ['A', 'A', 'B', 'A'], 'X': [1, 2, 3, 4]}],
  'A',
  '!A && Name == "A"',
  [{'Idetname': 'A', 'A': [False, False], 'Name': ['A', 'A'], 'X': [2, 4]}]),
 ('bool_column_same_as_string_value_complex',
  [{'Idetname': 'A', 'A': [True, False, True, False], 'Name': ['A', 'A', 'B', 'A'], 'X': [1, 2, 3, 4]}],
  'A',
  '(A && Name != "A") || (!A && Name == "A")',
  [{'Idetname': 'A', 'A': [False, True, False], 'Name': ['A', 'B', 'A'], 'X': [2, 3, 4]}]),
 ('bool_identifier_prefix_A_AA',
  [{'Idetname': 'A',
    'A': [True, False, True],
    'AA': [False, True, True],
    'A1': [True, True, False],
    'X': [1, 2, 3]}],
  'A',
  'A && AA',
  [{'Idetname': 'A', 'A': [True], 'AA': [True], 'A1': [False], 'X': [3]}]),
 ('bool_identifier_prefix_A_A1',
  [{'Idetname': 'A',
    'A': [True, False, True],
    'AA': [False, True, True],
    'A1': [True, True, False],
    'X': [1, 2, 3]}],
  'A',
  'A || A1',
  [{'Idetname': 'A',
    'A': [True, False, True],
    'AA': [False, True, True],
    'A1': [True, True, False],
    'X': [1, 2, 3]}]),
 ('bool_identifier_prefix_all_three',
  [{'Idetname': 'A',
    'A': [True, False, True],
    'AA': [False, True, True],
    'A1': [True, True, False],
    'X': [1, 2, 3]}],
  'A',
  '(A && !AA) || (!A && A1) || (AA && !A1)',
  [{'Idetname': 'A',
    'A': [True, False, True],
    'AA': [False, True, True],
    'A1': [True, True, False],
    'X': [1, 2, 3]}]),
 ('bool_column_same_as_detector_AA',
  [{'Idetname': 'AA', 'AA': [True, False, True], 'A': [False, True, True], 'X': [1, 2, 3]}],
  'AA',
  '(AA && A) || (!AA && !A)',
  [{'Idetname': 'AA', 'AA': [True], 'A': [True], 'X': [3]}]),
 ('bool_detector_name_prefix_of_column',
  [{'Idetname': 'AA', 'AA': [True, False, True], 'A': [False, True, True], 'X': [1, 2, 3]}],
  'A',
  '(AA || A)',
  [{'Idetname': 'AA', 'AA': [True, False, True], 'A': [False, True, True], 'X': [1, 2, 3]}]),
 ('quoted_detector_with_bool_vector',
  [{'Idetname': 'Det"A', 'Flag': [True, False, True], 'X': [1, 2, 3]}],
  'Det"A',
  'Flag && !(!Flag)',
  [{'Idetname': 'Det"A', 'Flag': [True, True], 'X': [1, 3]}]),
 ('backslash_detector_with_two_bool_vectors',
  [{'Idetname': 'Det\\A', 'A': [True, False, True], 'B': [False, False, True], 'X': [1, 2, 3]}],
  'Det\\A',
  '(A && B) || (!A && !B)',
  [{'Idetname': 'Det\\A', 'A': [False, True], 'B': [False, True], 'X': [2, 3]}]),
 ('compound_bool_target_and_unlisted',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [False, False, True, True], 'X': [1, 2, 3, 4]},
   {'Idetname': 'B', 'P': [True, False, True, False], 'Q': [False, False, True, True], 'X': [5, 6, 7, 8]},
   {'Idetname': 'C', 'P': [False, False], 'Q': [True, False], 'X': [9, 10]}],
  'A',
  '(P && Q) || (!P && !Q)',
  [{'Idetname': 'A', 'P': [False, True], 'Q': [False, True], 'X': [2, 3]},
   {'Idetname': 'B', 'P': [True, False, True, False], 'Q': [False, False, True, True], 'X': [5, 6, 7, 8]},
   {'Idetname': 'C', 'P': [False, False], 'Q': [True, False], 'X': [9, 10]}]),
 ('two_detectors_opposite_bool_rules',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [False, False, True, True], 'X': [1, 2, 3, 4]},
   {'Idetname': 'B', 'P': [True, False, True, False], 'Q': [False, False, True, True], 'X': [5, 6, 7, 8]},
   {'Idetname': 'C', 'P': [False, False], 'Q': [True, False], 'X': [9, 10]}],
  ['A', 'B'],
  ['P', '!P'],
  [{'Idetname': 'A', 'P': [True, True], 'Q': [False, True], 'X': [1, 3]},
   {'Idetname': 'B', 'P': [False, False], 'Q': [False, True], 'X': [6, 8]},
   {'Idetname': 'C', 'P': [False, False], 'Q': [True, False], 'X': [9, 10]}]),
 ('two_detectors_xnor_xor',
  [{'Idetname': 'A', 'P': [True, False, True, False], 'Q': [False, False, True, True], 'X': [1, 2, 3, 4]},
   {'Idetname': 'B', 'P': [True, False, True, False], 'Q': [False, False, True, True], 'X': [5, 6, 7, 8]},
   {'Idetname': 'C', 'P': [False, False], 'Q': [True, False], 'X': [9, 10]}],
  ['A', 'B'],
  ['(P && Q) || (!P && !Q)', '(P && !Q) || (!P && Q)'],
  [{'Idetname': 'A', 'P': [False, True], 'Q': [False, True], 'X': [2, 3]},
   {'Idetname': 'B', 'P': [True, False], 'Q': [False, True], 'X': [5, 8]},
   {'Idetname': 'C', 'P': [False, False], 'Q': [True, False], 'X': [9, 10]}]),
 ('two_detectors_three_bool_columns',
  [{'Idetname': 'A',
    'P': [True, False, True],
    'Q': [True, False, False],
    'R': [False, True, True],
    'X': [1, 2, 3]},
   {'Idetname': 'B',
    'P': [False, True, False],
    'Q': [True, True, False],
    'R': [True, False, False],
    'X': [4, 5, 6]},
   {'Idetname': 'Z', 'P': [False], 'Q': [False], 'R': [False], 'X': [7]}],
  ['A', 'B'],
  ['P && (Q || R)', '!P && (Q || !R)'],
  [{'Idetname': 'A', 'P': [True, True], 'Q': [True, False], 'R': [False, True], 'X': [1, 3]},
   {'Idetname': 'B', 'P': [False, False], 'Q': [True, False], 'R': [True, False], 'X': [4, 6]},
   {'Idetname': 'Z', 'P': [False], 'Q': [False], 'R': [False], 'X': [7]}]),
 ('same_detector_two_rows_distinct_bool_masks',
  [{'Idetname': 'A', 'P': [True, False, True], 'Q': [False, False, True], 'X': [1, 2, 3]},
   {'Idetname': 'A', 'P': [False, True, False], 'Q': [False, True, True], 'X': [4, 5, 6]}],
  'A',
  '(P && Q) || (!P && !Q)',
  [{'Idetname': 'A', 'P': [False, True], 'Q': [False, True], 'X': [2, 3]},
   {'Idetname': 'A', 'P': [False, True], 'Q': [False, True], 'X': [4, 5]}]),
 ('long_bool_vectors_xnor',
  [{'Idetname': 'A',
    'P': [True, False, True, False, True, False, True, False],
    'Q': [False, False, True, True, False, True, True, False],
    'X': [1, 2, 3, 4, 5, 6, 7, 8]}],
  'A',
  '(P && Q) || (!P && !Q)',
  [{'Idetname': 'A', 'P': [False, True, True, False], 'Q': [False, True, True, False], 'X': [2, 3, 7, 8]}]),
 ('bool_mask_applies_to_mixed_aligned_vectors',
  [{'Idetname': 'A',
    'P': [True, False, True, False],
    'Q': [False, True, True, False],
    'I': [10, 20, 30, 40],
    'D': [1.5, 2.5, 3.5, 4.5],
    'S': ['x', 'y', 'z', 'w']}],
  'A',
  '(P && Q) || (!P && !Q)',
  [{'Idetname': 'A',
    'P': [True, False],
    'Q': [True, False],
    'I': [30, 40],
    'D': [3.5, 4.5],
    'S': ['z', 'w']}]),
 ('all_false_vectors_xnor_keeps_all',
  [{'Idetname': 'A', 'P': [False, False, False], 'Q': [False, False, False], 'X': [1, 2, 3]}],
  'A',
  '(P && Q) || (!P && !Q)',
  [{'Idetname': 'A', 'P': [False, False, False], 'Q': [False, False, False], 'X': [1, 2, 3]}]),
 ('all_true_vectors_xor_rejects_row',
  [{'Idetname': 'A', 'P': [True, True, True], 'Q': [True, True, True], 'X': [1, 2, 3]}],
  'A',
  '(P && !Q) || (!P && Q)',
  []),
 ('single_element_bool_vectors',
  [{'Idetname': 'A', 'P': [False], 'Q': [False], 'X': [99]}],
  'A',
  '(P && Q) || (!P && !Q)',
  [{'Idetname': 'A', 'P': [False], 'Q': [False], 'X': [99]}])]


# ===========================================================================
# Test collection
# ===========================================================================


def _case_tests(
    group_name: str,
    cases,
):
    tests = []

    for (
        name,
        rows,
        detectors,
        cuts,
        expected,
    ) in cases:

        def run(
            rows=rows,
            detectors=detectors,
            cuts=cuts,
            expected=expected,
        ):
            check_detector_filter(
                rows,
                detectors,
                cuts,
                expected,
            )

        tests.append(
            (
                f"{group_name}.{name}",
                run,
            )
        )

    return tests


def _multi_case_tests(
    group_name: str,
    cases,
):
    tests = []

    for (
        name,
        dataframe_rows,
        detectors,
        cuts,
        expected,
    ) in cases:

        def run(
            dataframe_rows=dataframe_rows,
            detectors=detectors,
            cuts=cuts,
            expected=expected,
        ):
            check_detector_filter_many(
                dataframe_rows,
                detectors,
                cuts,
                expected,
            )

        tests.append(
            (
                f"{group_name}.{name}",
                run,
            )
        )

    return tests


def collect_tests():
    tests = []

    tests.extend(
        _case_tests(
            "scalar",
            SCALAR_CASES,
        )
    )

    tests.extend(
        _case_tests(
            "vector",
            VECTOR_CASES,
        )
    )
    

    standalone = [
        test_char_detector_scalar_cut,
        test_char_detector_two_detectors,
        test_char_detector_vector_cut,
        test_char_detector_string_vector_cut,
        test_custom_detector_column_scalar,
        test_custom_detector_column_two_detectors,
        test_custom_detector_column_vector,
        test_custom_char_detector_column,
        test_detector_name_underscore_digits,
        test_detector_name_parentheses_and_dash,
        test_char_detector_three_rules,
        test_char_detector_bool_vector,
    ]

    tests.extend(
        _case_tests(
            "weird",
            WEIRD_CASES,
        )
    )

    tests.extend(
        (test.__name__, test)
        for test in standalone
    )

    tests.extend(
        _multi_case_tests(
            "multi",
            MULTI_CASES,
        )
    )

    api_tests = [
        test_single_dataframe_returns_single_dataframe,
        test_dataframe_list_returns_list,
        test_tuple_dataframe_input_returns_list_like_existing_contract,
        test_many_rules_one_row_each,
        test_multiple_rules_with_vector_and_scalar_rows,
        test_large_combined_logic_known_output,
    ]

    tests.extend(
        (f"api.{test.__name__}", test)
        for test in api_tests
    )

    assert len(tests) == 150, (
        f"Test suite must contain exactly 150 tests, got {len(tests)}."
    )

    return tests


# ===========================================================================
# Runner
# ===========================================================================


def run_all_tests() -> int:
    tests = collect_tests()

    passed = 0
    failures = []

    print(
        f"Running {len(tests)} "
        "detector_filter_cut_rdataframe tests...\n"
    )

    for index, (
        name,
        test,
    ) in enumerate(
        tests,
        start=1,
    ):
        try:
            test()

        except Exception as error:
            failures.append(
                (
                    name,
                    error,
                )
            )

            print(
                f"[{index:03d}/{len(tests):03d}] "
                f"FAIL  {name}: "
                f"{type(error).__name__}: "
                f"{error}"
            )

        else:
            passed += 1

            print(
                f"[{index:03d}/{len(tests):03d}] "
                f"PASS  {name}"
            )

    print(
        "\n"
        + "=" * 72
    )

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