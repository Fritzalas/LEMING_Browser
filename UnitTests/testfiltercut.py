"""
150 standalone tests for global_filter_cut_rdataframe.

Each test does only:

    1. Create an input ROOT.RDataFrame.
    2. Call global_filter_cut_rdataframe(dataframe, cut).
    3. Materialize the output.
    4. Compare it with the expected result.

Run with:

    python test_global_filter_cut_rdataframe_standalone.py
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

from Helpers.Filter.general_apply_filter import (
    global_filter_cut_rdataframe,
)


# ===========================================================================
# Input RDataFrame construction
# ===========================================================================


class CharArray:
    """
    Marker used ONLY by the test-data builder.

    CharArray("Muon_Entrance")

    creates:

        ROOT::VecOps::RVec<Char_t>

    representing ONE C-style string.

    A normal Python list[str], instead, creates:

        ROOT::VecOps::RVec<std::string>
    """

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
            return (
                "std::numeric_limits<double>::quiet_NaN()"
            )

        if math.isinf(value):
            if value > 0:
                return (
                    "std::numeric_limits<double>::infinity()"
                )

            return (
                "-std::numeric_limits<double>::infinity()"
            )

        return repr(value)

    if isinstance(value, str):
        escaped = _escape_cpp_string(value)

        return (
            'std::string{"'
            + escaped
            + '"}'
        )

    raise TypeError(
        f"Unsupported scalar test value: {value!r}"
    )


def _infer_vector_cpp_type(
    all_rows: list[list[Any]],
) -> str:
    flattened = [
        value
        for row in all_rows
        for value in row
    ]

    if not flattened:
        return "int"

    if all(
        isinstance(value, bool)
        for value in flattened
    ):
        return "bool"

    if all(
        isinstance(value, str)
        for value in flattened
    ):
        return "std::string"

    if any(
        isinstance(value, float)
        for value in flattened
    ):
        return "double"

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


def _cpp_char_array(
    value: str,
) -> str:
    """
    Construct a null-terminated RVec<Char_t>.
    """

    encoded = value.encode("utf-8")

    values = [
        str(byte)
        for byte in encoded
    ]

    # Null terminator.
    values.append("0")

    return (
        "ROOT::VecOps::RVec<Char_t>{"
        + ", ".join(values)
        + "}"
    )


def _column_expression(
    values: list[Any],
) -> str:
    """
    Create a rdfentry_-dependent C++ expression for one column.

    Supported test input forms:

        10
            -> scalar int

        10.5
            -> scalar double

        True
            -> scalar bool

        "Muon"
            -> std::string

        [1, 2, 3]
            -> RVec<int>

        [True, False, True]
            -> RVec<bool>

        ["Kosmas", "Muon", "you"]
            -> RVec<std::string>

        CharArray("Muon_Entrance")
            -> RVec<Char_t>
    """

    first = values[0]

    # ------------------------------------------------------------------
    # One C-style string: RVec<Char_t>
    # ------------------------------------------------------------------

    if isinstance(first, CharArray):
        literals = [
            _cpp_char_array(value.value)
            for value in values
        ]

        fallback = (
            "ROOT::VecOps::RVec<Char_t>{0}"
        )

    # ------------------------------------------------------------------
    # Genuine RVec
    # ------------------------------------------------------------------

    elif isinstance(first, (list, tuple)):
        rows = [
            list(value)
            for value in values
        ]

        cpp_type = _infer_vector_cpp_type(
            rows
        )

        literals = [
            _cpp_vector(
                row,
                cpp_type,
            )
            for row in rows
        ]

        fallback = (
            f"ROOT::VecOps::RVec<{cpp_type}>{{}}"
        )

    # ------------------------------------------------------------------
    # Scalar
    # ------------------------------------------------------------------

    else:
        literals = [
            _cpp_scalar(value)
            for value in values
        ]

        if isinstance(first, str):
            fallback = 'std::string{""}'

        elif isinstance(first, bool):
            fallback = "false"

        elif isinstance(first, float):
            fallback = "0.0"

        else:
            fallback = "0"

    expression = fallback

    for index in reversed(
        range(len(literals))
    ):
        expression = (
            f"(rdfentry_ == {index}ULL ? "
            f"{literals[index]} : "
            f"{expression})"
        )

    return expression


def make_dataframe(
    rows: list[dict[str, Any]],
):
    """
    Build an RDataFrame containing exactly `rows`.
    """

    assert rows

    columns = list(rows[0])

    assert all(
        list(row) == columns
        for row in rows
    )

    dataframe = ROOT.RDataFrame(
        len(rows)
    )

    for column in columns:
        dataframe = dataframe.Define(
            column,
            _column_expression(
                [
                    row[column]
                    for row in rows
                ]
            ),
        )

    return dataframe


# ===========================================================================
# Result conversion
# ===========================================================================


def _python_value(value: Any) -> Any:
    # Strings must be handled before generic iteration.
    if isinstance(value, str):
        return value

    if isinstance(value, bytes):
        return value.decode(
            "utf-8",
            errors="replace",
        )

    if hasattr(value, "tolist"):
        converted = value.tolist()

        # numpy/object values can themselves contain
        # strings, vectors, etc.
        return _python_value(converted)

    if hasattr(value, "item"):
        converted = value.item()

        # Avoid returning a wrapped numpy scalar.
        if converted is not value:
            return _python_value(converted)

    if isinstance(value, (list, tuple)):
        return [
            _python_value(item)
            for item in value
        ]

    try:
        # PyROOT RVec proxy.
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

    count = len(
        arrays[columns[0]]
    )

    return [
        {
            column: _python_value(
                arrays[column][row]
            )
            for column in columns
        }
        for row in range(count)
    ]


# ===========================================================================
# Generic test function
# ===========================================================================


def check_filter(
    rows: list[dict[str, Any]],
    cut: str | list[str] | None,
    expected: list[dict[str, Any]],
    *,
    columns: list[str] | None = None,
):
    """
    The actual test:

        input dataframe
            ↓
        global_filter_cut_rdataframe
            ↓
        output dataframe
            ↓
        compare with expected
    """

    dataframe = make_dataframe(rows)

    result = global_filter_cut_rdataframe(
        dataframe,
        cut,
    )

    if columns is None:
        columns = list(rows[0])

    actual = materialize(
        result,
        columns,
    )

    assert actual == expected, (
        "\n"
        f"Cut:\n{cut}\n\n"
        f"Expected:\n{expected}\n\n"
        f"Actual:\n{actual}"
    )


# ===========================================================================
# Scalar tests
# ===========================================================================


SCALAR_CASES = [
    (
        "numeric_scalar",
        [
            {"X": 1, "Y": 2},
            {"X": 2, "Y": 8},
            {"X": 3, "Y": 12},
        ],
        "Y > 5",
        [
            {"X": 2, "Y": 8},
            {"X": 3, "Y": 12},
        ],
    ),

    (
        "scalar_bool",
        [
            {"X": 1, "Good": False},
            {"X": 2, "Good": True},
            {"X": 3, "Good": False},
        ],
        "Good",
        [
            {"X": 2, "Good": True},
        ],
    ),

    (
        "scalar_bool_complex",
        [
            {
                "X": 1,
                "Good": True,
                "Force": False,
            },
            {
                "X": 2,
                "Good": False,
                "Force": True,
            },
            {
                "X": 3,
                "Good": False,
                "Force": False,
            },
        ],
        "(Good && X < 3) || Force",
        [
            {
                "X": 1,
                "Good": True,
                "Force": False,
            },
            {
                "X": 2,
                "Good": False,
                "Force": True,
            },
        ],
    ),

    (
        "scalar_string",
        [
            {
                "Name": "Kosmas",
                "X": 1,
            },
            {
                "Name": "Muon_Entrance",
                "X": 2,
            },
            {
                "Name": "you",
                "X": 3,
            },
        ],
        'Name == "Muon_Entrance"',
        [
            {
                "Name": "Muon_Entrance",
                "X": 2,
            },
        ],
    ),

    (
        "scalar_string_bool_numeric_complex",
        [
            {
                "Name": "Muon_Entrance",
                "Good": True,
                "Force": False,
                "Run": 10,
            },
            {
                "Name": "Tracker",
                "Good": False,
                "Force": True,
                "Run": 20,
            },
            {
                "Name": "Muon_Entrance",
                "Good": False,
                "Force": False,
                "Run": 30,
            },
            {
                "Name": "Tracker",
                "Good": True,
                "Force": False,
                "Run": 50,
            },
        ],
        (
            "("
            'Name == "Muon_Entrance" '
            "&& Good"
            ") || ("
            "Force "
            "&& Run >= 20 "
            "&& Run < 40"
            ")"
        ),
        [
            {
                "Name": "Muon_Entrance",
                "Good": True,
                "Force": False,
                "Run": 10,
            },
            {
                "Name": "Tracker",
                "Good": False,
                "Force": True,
                "Run": 20,
            },
        ],
    ),
]


# ===========================================================================
# Numeric vector tests
# ===========================================================================


VECTOR_CASES = [
    (
        "numeric_vector",
        [
            {
                "Time": [1, 2, 3],
                "Energy": [34, 12, 32],
            },
        ],
        "Energy > 30",
        [
            {
                "Time": [1, 3],
                "Energy": [34, 32],
            },
        ],
    ),

    (
        "complex_numeric_vectors",
        [
            {
                "X": [1, 2, 3, 4, 5],
                "Y": [10, 50, 20, 80, 100],
                "Z": [5, 4, 3, 2, 1],
            },
        ],
        (
            "(Y > 40 && Z < 5) "
            "|| (X == 1 && Z == 5)"
        ),
        [
            {
                "X": [1, 2, 4, 5],
                "Y": [10, 50, 80, 100],
                "Z": [5, 4, 2, 1],
            },
        ],
    ),
]


# ===========================================================================
# RVec<bool> tests
# ===========================================================================


BOOL_VECTOR_CASES = [
    (
        "bool_vector_direct",
        [
            {
                "X": [1, 2, 3, 4],
                "Good": [
                    True,
                    False,
                    True,
                    False,
                ],
            },
        ],
        "Good",
        [
            {
                "X": [1, 3],
                "Good": [True, True],
            },
        ],
    ),

    (
        "bool_vector_numeric",
        [
            {
                "Energy": [
                    20,
                    60,
                    100,
                    180,
                    500,
                ],
                "Time": [
                    1,
                    2,
                    3,
                    4,
                    5,
                ],
                "Good": [
                    True,
                    True,
                    False,
                    True,
                    False,
                ],
            },
        ],
        (
            "Good "
            "&& Energy >= 50 "
            "&& Energy < 200"
        ),
        [
            {
                "Energy": [60, 180],
                "Time": [2, 4],
                "Good": [True, True],
            },
        ],
    ),

    (
        "two_bool_vectors_complex",
        [
            {
                "Energy": [
                    20,
                    50,
                    80,
                    120,
                    250,
                    500,
                ],
                "A": [
                    True,
                    False,
                    True,
                    False,
                    True,
                    False,
                ],
                "B": [
                    False,
                    True,
                    False,
                    True,
                    False,
                    True,
                ],
                "Time": [
                    1,
                    2,
                    3,
                    4,
                    5,
                    6,
                ],
            },
        ],
        (
            "(A && Energy >= 70) "
            "|| "
            "(B && Energy >= 100 && Energy < 300)"
        ),
        [
            {
                "Energy": [
                    80,
                    120,
                    250,
                ],
                "A": [
                    True,
                    False,
                    True,
                ],
                "B": [
                    False,
                    True,
                    False,
                ],
                "Time": [
                    3,
                    4,
                    5,
                ],
            },
        ],
    ),
]


# ===========================================================================
# RVec<std::string> tests
# ===========================================================================


STRING_VECTOR_CASES = [
    (
        "string_vector",
        [
            {
                "Name": [
                    "Kosmas",
                    "Muon_Entrance",
                    "you",
                ],
                "Energy": [
                    10,
                    50,
                    100,
                ],
                "Time": [
                    1,
                    2,
                    3,
                ],
            },
        ],
        'Name == "Muon_Entrance"',
        [
            {
                "Name": [
                    "Muon_Entrance",
                ],
                "Energy": [50],
                "Time": [2],
            },
        ],
    ),

    (
        "string_vector_not_equal",
        [
            {
                "Particle": [
                    "muon",
                    "electron",
                    "proton",
                    "muon",
                ],
                "Energy": [
                    10,
                    20,
                    30,
                    40,
                ],
            },
        ],
        'Particle != "muon"',
        [
            {
                "Particle": [
                    "electron",
                    "proton",
                ],
                "Energy": [
                    20,
                    30,
                ],
            },
        ],
    ),

    (
        "string_bool_numeric_vector",
        [
            {
                "Particle": [
                    "muon",
                    "electron",
                    "muon",
                    "proton",
                    "muon",
                ],
                "Energy": [
                    20,
                    500,
                    80,
                    300,
                    150,
                ],
                "Good": [
                    True,
                    True,
                    False,
                    True,
                    True,
                ],
                "Time": [
                    1,
                    2,
                    3,
                    4,
                    5,
                ],
            },
        ],
        (
            'Particle == "muon" '
            "&& Good "
            "&& Energy >= 50 "
            "&& Energy < 200"
        ),
        [
            {
                "Particle": [
                    "muon",
                ],
                "Energy": [
                    150,
                ],
                "Good": [
                    True,
                ],
                "Time": [
                    5,
                ],
            },
        ],
    ),

    (
        "string_vector_nested_or",
        [
            {
                "Particle": [
                    "electron",
                    "muon",
                    "proton",
                    "gamma",
                    "muon",
                    "proton",
                ],
                "Energy": [
                    150,
                    20,
                    300,
                    1000,
                    90,
                    500,
                ],
                "Good": [
                    False,
                    True,
                    True,
                    True,
                    True,
                    False,
                ],
                "Triggered": [
                    False,
                    True,
                    False,
                    True,
                    False,
                    True,
                ],
            },
        ],
        (
            "("
            'Particle == "muon" '
            "&& Good"
            ") || ("
            'Particle == "proton" '
            "&& Energy > 200"
            ") || ("
            'Particle == "electron" '
            "&& !Good "
            "&& Energy > 100"
            ")"
        ),
        [
            {
                "Particle": [
                    "electron",
                    "muon",
                    "proton",
                    "muon",
                    "proton",
                ],
                "Energy": [
                    150,
                    20,
                    300,
                    90,
                    500,
                ],
                "Good": [
                    False,
                    True,
                    True,
                    True,
                    False,
                ],
                "Triggered": [
                    False,
                    True,
                    False,
                    False,
                    True,
                ],
            },
        ],
    ),
]


# ===========================================================================
# Mixed scalar + vector tests
# ===========================================================================


MIXED_CASES = [
    (
        "scalar_bool_and_vectors",
        [
            {
                "Enabled": True,
                "Energy": [
                    20,
                    60,
                    100,
                    180,
                ],
                "Good": [
                    False,
                    True,
                    True,
                    False,
                ],
            },
            {
                "Enabled": False,
                "Energy": [
                    500,
                    600,
                    700,
                ],
                "Good": [
                    True,
                    True,
                    True,
                ],
            },
        ],
        (
            "Enabled "
            "&& Good "
            "&& Energy >= 50"
        ),
        [
            {
                "Enabled": True,
                "Energy": [
                    60,
                    100,
                ],
                "Good": [
                    True,
                    True,
                ],
            },
        ],
    ),

    (
        "scalar_string_and_vector_string",
        [
            {
                "RunType": "Physics",
                "Particle": [
                    "electron",
                    "muon",
                    "proton",
                ],
                "Energy": [
                    300,
                    50,
                    400,
                ],
            },
            {
                "RunType": "Calibration",
                "Particle": [
                    "muon",
                    "muon",
                ],
                "Energy": [
                    500,
                    600,
                ],
            },
        ],
        (
            'RunType == "Physics" '
            '&& Particle == "muon" '
            "&& Energy > 30"
        ),
        [
            {
                "RunType": "Physics",
                "Particle": [
                    "muon",
                ],
                "Energy": [
                    50,
                ],
            },
        ],
    ),
]


# ===========================================================================
# RVec<Char_t> tests
# ===========================================================================


def test_char_array_equal():
    dataframe = make_dataframe([
        {
            "Detector": CharArray(
                "Muon_Entrance"
            ),
            "Run": 1,
        },
        {
            "Detector": CharArray(
                "Tracker"
            ),
            "Run": 2,
        },
        {
            "Detector": CharArray(
                "Muon_Entrance"
            ),
            "Run": 3,
        },
    ])

    result = global_filter_cut_rdataframe(
        dataframe,
        'Detector == "Muon_Entrance"',
    )

    actual = materialize(
        result,
        ["Run"],
    )

    assert actual == [
        {"Run": 1},
        {"Run": 3},
    ]


def test_char_array_not_equal():
    dataframe = make_dataframe([
        {
            "Detector": CharArray("Kosmas"),
            "Run": 1,
        },
        {
            "Detector": CharArray(
                "Muon_Entrance"
            ),
            "Run": 2,
        },
        {
            "Detector": CharArray("you"),
            "Run": 3,
        },
    ])

    result = global_filter_cut_rdataframe(
        dataframe,
        'Detector != "Muon_Entrance"',
    )

    actual = materialize(
        result,
        ["Run"],
    )

    assert actual == [
        {"Run": 1},
        {"Run": 3},
    ]


def test_char_array_bool_numeric():
    dataframe = make_dataframe([
        {
            "Detector": CharArray(
                "Muon_Entrance"
            ),
            "Enabled": True,
            "Run": 10,
        },
        {
            "Detector": CharArray(
                "Muon_Entrance"
            ),
            "Enabled": False,
            "Run": 20,
        },
        {
            "Detector": CharArray(
                "Tracker"
            ),
            "Enabled": True,
            "Run": 30,
        },
    ])

    result = global_filter_cut_rdataframe(
        dataframe,
        (
            'Detector == "Muon_Entrance" '
            "&& Enabled "
            "&& Run < 20"
        ),
    )

    actual = materialize(
        result,
        [
            "Enabled",
            "Run",
        ],
    )

    assert actual == [
        {
            "Enabled": True,
            "Run": 10,
        },
    ]


# ===========================================================================
# Complicated everything-at-once tests
# ===========================================================================


def test_everything_mixed():
    dataframe = make_dataframe([
        {
            "Detector": CharArray(
                "Muon_Entrance"
            ),

            "EventGood": True,

            "Particle": [
                "electron",
                "muon",
                "proton",
                "muon",
                "muon",
                "gamma",
            ],

            "Good": [
                True,
                True,
                True,
                False,
                True,
                True,
            ],

            "Triggered": [
                False,
                False,
                True,
                True,
                False,
                True,
            ],

            "Energy": [
                200,
                60,
                300,
                120,
                180,
                1000,
            ],

            "Time": [
                1,
                2,
                3,
                4,
                5,
                6,
            ],
        },

        {
            "Detector": CharArray(
                "Tracker"
            ),

            "EventGood": True,

            "Particle": [
                "muon",
                "muon",
            ],

            "Good": [
                True,
                True,
            ],

            "Triggered": [
                True,
                True,
            ],

            "Energy": [
                500,
                600,
            ],

            "Time": [
                10,
                20,
            ],
        },

        {
            "Detector": CharArray(
                "Muon_Entrance"
            ),

            "EventGood": False,

            "Particle": [
                "muon",
                "proton",
            ],

            "Good": [
                True,
                True,
            ],

            "Triggered": [
                True,
                True,
            ],

            "Energy": [
                900,
                1000,
            ],

            "Time": [
                100,
                200,
            ],
        },
    ])

    cut = (
        'Detector == "Muon_Entrance" '
        "&& EventGood "
        "&& ("
        "("
        'Particle == "muon" '
        "&& Good "
        "&& Energy >= 50 "
        "&& Energy < 200"
        ") || ("
        'Particle == "proton" '
        "&& Triggered "
        "&& Energy >= 250"
        ")"
        ") "
        "&& Time >= 2"
    )

    result = global_filter_cut_rdataframe(
        dataframe,
        cut,
    )

    actual = materialize(
        result,
        [
            "EventGood",
            "Particle",
            "Good",
            "Triggered",
            "Energy",
            "Time",
        ],
    )

    expected = [
        {
            "EventGood": True,

            "Particle": [
                "muon",
                "proton",
                "muon",
            ],

            "Good": [
                True,
                True,
                True,
            ],

            "Triggered": [
                False,
                True,
                False,
            ],

            "Energy": [
                60,
                300,
                180,
            ],

            "Time": [
                2,
                3,
                5,
            ],
        },
    ]

    assert actual == expected


def test_deep_nested_everything():
    dataframe = make_dataframe([
        {
            "Detector": CharArray(
                "Muon_Entrance"
            ),

            "Force": False,

            "Particle": [
                "muon",
                "electron",
                "proton",
                "muon",
                "gamma",
                "proton",
                "muon",
            ],

            "A": [
                True,
                False,
                True,
                False,
                True,
                False,
                True,
            ],

            "B": [
                False,
                True,
                False,
                True,
                True,
                True,
                True,
            ],

            "Energy": [
                40,
                200,
                250,
                90,
                1000,
                500,
                30,
            ],

            "Time": [
                1,
                2,
                3,
                4,
                5,
                6,
                7,
            ],
        },
    ])

    cut = (
        'Detector == "Muon_Entrance" '
        "&& ("
        "("
        'Particle == "muon" '
        "&& ("
        "(A && Energy > 30) "
        "|| "
        "(B && Energy >= 80)"
        ")"
        ") || ("
        'Particle == "proton" '
        "&& !A "
        "&& B "
        "&& Energy > 400"
        ") || ("
        'Particle != "gamma" '
        "&& A "
        "&& Energy >= 200"
        ")"
        ") "
        "&& Time <= 6"
    )

    result = global_filter_cut_rdataframe(
        dataframe,
        cut,
    )

    actual = materialize(
        result,
        [
            "Particle",
            "A",
            "B",
            "Energy",
            "Time",
        ],
    )

    expected = [
        {
            "Particle": [
                "muon",
                "proton",
                "muon",
                "proton",
            ],

            "A": [
                True,
                True,
                False,
                False,
            ],

            "B": [
                False,
                False,
                True,
                True,
            ],

            "Energy": [
                40,
                250,
                90,
                500,
            ],

            "Time": [
                1,
                3,
                4,
                6,
            ],
        },
    ]

    assert actual == expected


def test_multiple_cut_list_everything():
    dataframe = make_dataframe([
        {
            "Detector": CharArray(
                "Muon_Entrance"
            ),

            "Enabled": True,

            "Particle": [
                "muon",
                "electron",
                "muon",
                "proton",
                "gamma",
            ],

            "Good": [
                True,
                True,
                False,
                True,
                True,
            ],

            "Energy": [
                70,
                200,
                150,
                300,
                500,
            ],

            "Time": [
                1,
                2,
                3,
                4,
                5,
            ],
        },
    ])

    cuts = [
        'Detector == "Muon_Entrance"',
        "Enabled",
        (
            'Particle == "muon" '
            '|| Particle == "proton"'
        ),
        "Energy >= 50",
        "Good || Energy > 250",
        "Time <= 4",
    ]

    result = global_filter_cut_rdataframe(
        dataframe,
        cuts,
    )

    actual = materialize(
        result,
        [
            "Enabled",
            "Particle",
            "Good",
            "Energy",
            "Time",
        ],
    )

    expected = [
        {
            "Enabled": True,

            "Particle": [
                "muon",
                "proton",
            ],

            "Good": [
                True,
                True,
            ],

            "Energy": [
                70,
                300,
            ],

            "Time": [
                1,
                4,
            ],
        },
    ]

    assert actual == expected


def test_no_vector_element_survives():
    dataframe = make_dataframe([
        {
            "Detector": CharArray(
                "Muon_Entrance"
            ),

            "Enabled": True,

            "Particle": [
                "electron",
                "proton",
                "gamma",
            ],

            "Good": [
                True,
                True,
                True,
            ],

            "Energy": [
                500,
                600,
                700,
            ],
        },
    ])

    result = global_filter_cut_rdataframe(
        dataframe,
        (
            'Detector == "Muon_Entrance" '
            "&& Enabled "
            '&& Particle == "muon" '
            "&& Good "
            "&& Energy > 100"
        ),
    )

    actual = materialize(
        result,
        ["Energy"],
    )

    assert actual == []


# ===========================================================================
# API behavior
# ===========================================================================


def test_single_dataframe_returns_single_dataframe():
    dataframe = make_dataframe([
        {"X": 1},
        {"X": 2},
        {"X": 3},
    ])

    result = global_filter_cut_rdataframe(
        dataframe,
        "X >= 2",
    )

    assert not isinstance(
        result,
        list,
    )

    assert materialize(
        result,
        ["X"],
    ) == [
        {"X": 2},
        {"X": 3},
    ]


def test_dataframe_list_returns_list():
    first = make_dataframe([
        {"X": 1},
        {"X": 5},
    ])

    second = make_dataframe([
        {"X": 2},
        {"X": 10},
    ])

    result = global_filter_cut_rdataframe(
        [
            first,
            second,
        ],
        "X > 3",
    )

    assert isinstance(
        result,
        list,
    )

    assert materialize(
        result[0],
        ["X"],
    ) == [
        {"X": 5},
    ]

    assert materialize(
        result[1],
        ["X"],
    ) == [
        {"X": 10},
    ]


def test_none_is_noop():
    rows = [
        {
            "X": [1, 2, 3],
            "Y": [4, 5, 6],
        },
    ]

    check_filter(
        rows,
        None,
        rows,
    )


def test_blank_is_noop():
    rows = [
        {
            "X": [1, 2, 3],
            "Y": [4, 5, 6],
        },
    ]

    check_filter(
        rows,
        "   ",
        rows,
    )


def test_mismatched_vector_lengths_fail():
    dataframe = make_dataframe([
        {
            "X": [
                1,
                2,
                3,
            ],

            "Y": [
                10,
                20,
            ],
        },
    ])

    result = global_filter_cut_rdataframe(
        dataframe,
        "X > 1 && Y > 1",
    )

    try:
        materialize(
            result,
            ["X", "Y"],
        )

    except Exception:
        return

    raise AssertionError(
        "Expected mismatched vector lengths "
        "to fail during evaluation."
    )


# ===========================================================================
# Previous regression suite retained
# ===========================================================================

PREVIOUS_SCALAR_CASES = [
    (
        "greater_than",
        [{"X": 1, "Y": 2}, {"X": 2, "Y": 5}, {"X": 3, "Y": 7}],
        "Y > 4",
        [{"X": 2, "Y": 5}, {"X": 3, "Y": 7}],
    ),
    (
        "greater_equal",
        [{"X": 1, "Y": 4}, {"X": 2, "Y": 5}],
        "Y >= 4",
        [{"X": 1, "Y": 4}, {"X": 2, "Y": 5}],
    ),
    (
        "less_than",
        [{"X": 1, "Y": -1}, {"X": 2, "Y": 0}, {"X": 3, "Y": 2}],
        "Y < 0",
        [{"X": 1, "Y": -1}],
    ),
    (
        "equal",
        [{"X": 1, "Y": 3}, {"X": 2, "Y": 4}],
        "Y == 3",
        [{"X": 1, "Y": 3}],
    ),
    (
        "not_equal",
        [{"X": 1, "Y": 3}, {"X": 2, "Y": 4}],
        "Y != 3",
        [{"X": 2, "Y": 4}],
    ),
    (
        "logical_and",
        [{"X": 1, "Y": 5}, {"X": 3, "Y": 5}, {"X": 3, "Y": 8}],
        "X > 1 && Y < 7",
        [{"X": 3, "Y": 5}],
    ),
    (
        "logical_or",
        [{"X": 1, "Y": 5}, {"X": 3, "Y": 5}, {"X": 3, "Y": 8}],
        "X == 1 || Y == 8",
        [{"X": 1, "Y": 5}, {"X": 3, "Y": 8}],
    ),
    (
        "parenthesized",
        [{"X": 1, "Y": 5}, {"X": 3, "Y": 5}, {"X": 3, "Y": 8}],
        "(X > 2 && Y < 6) || (X == 1)",
        [{"X": 1, "Y": 5}, {"X": 3, "Y": 5}],
    ),
    (
        "arithmetic",
        [{"X": 1, "Y": 5}, {"X": 3, "Y": 5}, {"X": 4, "Y": 8}],
        "X * 2 + Y >= 11",
        [{"X": 3, "Y": 5}, {"X": 4, "Y": 8}],
    ),
    (
        "floating_point",
        [{"X": 1, "Y": 2.5}, {"X": 2, "Y": 3.25}, {"X": 3, "Y": 4.5}],
        "Y > 3.0 && Y < 4.0",
        [{"X": 2, "Y": 3.25}],
    ),
    (
        "boolean_scalar",
        [{"X": 1, "Good": False}, {"X": 2, "Good": True}],
        "Good",
        [{"X": 2, "Good": True}],
    ),
    (
        "no_rows_match",
        [{"X": 1, "Y": 2}, {"X": 2, "Y": 3}],
        "Y > 100",
        [],
    ),
]

PREVIOUS_VECTOR_CASES = [
    (
        "single_vector_gt",
        [{"X": [1, 2, 3], "Y": [4, 2, 5], "Z": [6, 7, 1]}],
        "Y > 3",
        [{"X": [1, 3], "Y": [4, 5], "Z": [6, 1]}],
    ),
    (
        "two_vector_and",
        [{"X": [1, 2, 3], "Y": [4, 2, 5], "Z": [6, 7, 1]}],
        "Y > 3 && Z < 6",
        [{"X": [3], "Y": [5], "Z": [1]}],
    ),
    (
        "two_vector_or",
        [{"X": [1, 2, 3], "Y": [4, 2, 5], "Z": [6, 7, 1]}],
        "Y > 4 || Z == 6",
        [{"X": [1, 3], "Y": [4, 5], "Z": [6, 1]}],
    ),
    (
        "vector_equal",
        [{"X": [1, 2, 3], "Y": [4, 2, 4]}],
        "Y == 4",
        [{"X": [1, 3], "Y": [4, 4]}],
    ),
    (
        "vector_not_equal",
        [{"X": [1, 2, 3], "Y": [4, 2, 4]}],
        "Y != 4",
        [{"X": [2], "Y": [2]}],
    ),
    (
        "three_vector_conditions",
        [{"X": [1, 4, 7], "Y": [5, 5, 2], "Z": [1, 8, 3]}],
        "X > 2 && Y >= 5 && Z < 10",
        [{"X": [4], "Y": [5], "Z": [8]}],
    ),
    (
        "vector_arithmetic",
        [{"X": [1, 2, 3], "Y": [4, 5, 6]}],
        "X + Y >= 8",
        [{"X": [3], "Y": [6]}],
    ),
    (
        "vector_multiplication",
        [{"X": [1, 2, 4], "Y": [5, 3, 2]}],
        "X * Y > 6",
        [{"X": [4], "Y": [2]}],
    ),
    (
        "nested_parentheses",
        [{"X": [1, 2, 3, 4], "Y": [9, 2, 5, 1], "Z": [0, 8, 2, 7]}],
        "((X >= 3 && Y < 6) || Z == 8) && Z < 8",
        [{"X": [3, 4], "Y": [5, 1], "Z": [2, 7]}],
    ),
    (
        "negative_values",
        [{"X": [-3, -1, 0, 2], "Y": [1, 2, 3, 4]}],
        "X < 0 && Y >= 2",
        [{"X": [-1], "Y": [2]}],
    ),
    (
        "double_vectors",
        [{"X": [1.1, 2.2, 3.3], "Y": [0.5, 2.5, 4.5]}],
        "X > 2.0 && Y < 4.0",
        [{"X": [2.2], "Y": [2.5]}],
    ),
    (
        "all_elements_match",
        [{"X": [1, 2, 3], "Y": [4, 5, 6]}],
        "Y > 0",
        [{"X": [1, 2, 3], "Y": [4, 5, 6]}],
    ),
    (
        "no_elements_match_rejects_row",
        [{"X": [1, 2, 3], "Y": [4, 5, 6]}],
        "Y > 10",
        [],
    ),
    (
        "two_rows_different_masks",
        [
            {"X": [1, 2, 3], "Y": [2, 5, 7]},
            {"X": [10, 20, 30], "Y": [8, 1, 9]},
        ],
        "Y > 4",
        [
            {"X": [2, 3], "Y": [5, 7]},
            {"X": [10, 30], "Y": [8, 9]},
        ],
    ),
    (
        "one_of_two_rows_rejected",
        [
            {"X": [1, 2], "Y": [1, 2]},
            {"X": [3, 4], "Y": [8, 9]},
        ],
        "Y > 5",
        [{"X": [3, 4], "Y": [8, 9]}],
    ),
    (
        "four_aligned_vectors",
        [{"A": [1, 2, 3], "B": [4, 5, 6], "C": [7, 8, 9], "D": [10, 11, 12]}],
        "B >= 5 && D < 12",
        [{"A": [2], "B": [5], "C": [8], "D": [11]}],
    ),
    (
        "column_name_prefixes",
        [{"E": [1, 2, 3], "Energy": [4, 5, 6], "EnergyRaw": [7, 1, 9]}],
        "Energy > 4 && EnergyRaw > 5",
        [{"E": [3], "Energy": [6], "EnergyRaw": [9]}],
    ),
    (
        "complex_boolean_expression",
        [{"X": [1, 2, 3, 4], "Y": [2, 8, 4, 9], "Z": [7, 1, 5, 3]}],
        "(X <= 2 && Y >= 8) || (X > 2 && Z <= 3)",
        [{"X": [2, 4], "Y": [8, 9], "Z": [1, 3]}],
    ),
]

PREVIOUS_MIXED_CASES = [
    (
        "true_scalar_and_vector",
        [{"RunGood": True, "X": [1, 2, 3], "Y": [2, 5, 7]}],
        "RunGood && Y > 4",
        [{"RunGood": True, "X": [2, 3], "Y": [5, 7]}],
    ),
    (
        "false_scalar_rejects_vector_row",
        [{"RunGood": False, "X": [1, 2, 3], "Y": [2, 5, 7]}],
        "RunGood && Y > 4",
        [],
    ),
    (
        "scalar_threshold",
        [{"Threshold": 4, "X": [1, 2, 3], "Y": [2, 5, 7]}],
        "Y > Threshold",
        [{"Threshold": 4, "X": [2, 3], "Y": [5, 7]}],
    ),
    (
        "two_scalars_one_vector",
        [{"Low": 2, "High": 7, "X": [1, 2, 3, 4], "Y": [1, 3, 7, 8]}],
        "Y > Low && Y < High",
        [{"Low": 2, "High": 7, "X": [2], "Y": [3]}],
    ),
    (
        "scalar_or_vector_true_scalar_keeps_all",
        [{"Force": True, "X": [1, 2, 3], "Y": [0, 0, 0]}],
        "Force || Y > 4",
        [{"Force": True, "X": [1, 2, 3], "Y": [0, 0, 0]}],
    ),
    (
        "scalar_or_vector_false_scalar_uses_mask",
        [{"Force": False, "X": [1, 2, 3], "Y": [0, 5, 0]}],
        "Force || Y > 4",
        [{"Force": False, "X": [2], "Y": [5]}],
    ),
    (
        "mixed_arithmetic",
        [{"Offset": 2, "X": [1, 2, 3], "Y": [3, 4, 5]}],
        "X + Offset >= Y",
        [{"Offset": 2, "X": [1, 2, 3], "Y": [3, 4, 5]}],
    ),
    (
        "scalar_changes_per_row",
        [
            {"Threshold": 3, "X": [1, 2], "Y": [2, 4]},
            {"Threshold": 8, "X": [3, 4], "Y": [7, 9]},
        ],
        "Y > Threshold",
        [
            {"Threshold": 3, "X": [2], "Y": [4]},
            {"Threshold": 8, "X": [4], "Y": [9]},
        ],
    ),
    (
        "scalar_range_and_two_vectors",
        [{"Enabled": True, "Limit": 6, "X": [1, 2, 3], "Y": [4, 7, 5], "Z": [2, 1, 9]}],
        "Enabled && Y < Limit && Z > 1",
        [{"Enabled": True, "Limit": 6, "X": [1, 3], "Y": [4, 5], "Z": [2, 9]}],
    ),
    (
        "integer_scalar_used_twice",
        [{"Pivot": 3, "X": [1, 3, 5], "Y": [5, 3, 1]}],
        "X >= Pivot && Y <= Pivot",
        [{"Pivot": 3, "X": [3, 5], "Y": [3, 1]}],
    ),
]

def assert_filtered(rows, cut, expected):
    check_filter(rows, cut, expected)


def test_multiple_dataframes_are_filtered_independently():
    first = make_dataframe([
        {"X": [1, 2, 3], "Y": [2, 5, 7]},
    ])
    second = make_dataframe([
        {"X": [10, 20, 30], "Y": [8, 1, 9]},
    ])

    results = global_filter_cut_rdataframe([first, second], "Y > 4")

    assert materialize(results[0], ["X", "Y"]) == [
        {"X": [2, 3], "Y": [5, 7]},
    ]
    assert materialize(results[1], ["X", "Y"]) == [
        {"X": [10, 30], "Y": [8, 9]},
    ]

def test_three_mixed_dataframes_one_cut():
    dataframes = [
        make_dataframe([{"X": 1, "Y": 2}, {"X": 2, "Y": 8}]),
        make_dataframe([{"X": 3, "Y": 9}, {"X": 4, "Y": 1}]),
        make_dataframe([{"X": 5, "Y": 6}, {"X": 6, "Y": 7}]),
    ]

    results = global_filter_cut_rdataframe(dataframes, "Y >= 7")

    assert materialize(results[0], ["X", "Y"]) == [{"X": 2, "Y": 8}]
    assert materialize(results[1], ["X", "Y"]) == [{"X": 3, "Y": 9}]
    assert materialize(results[2], ["X", "Y"]) == [{"X": 6, "Y": 7}]

def test_chained_vector_cuts_apply_sequentially():
    rows = [{
        "X": [1, 2, 3, 4],
        "Y": [2, 5, 7, 9],
        "Z": [8, 6, 3, 1],
    }]
    expected = [{"X": [2,3], "Y": [5,7], "Z": [6,3]}]
    assert_filtered(rows, ["Y > 4", "Z > 2"], expected)

def test_chained_scalar_then_vector_cut():
    rows = [
        {"Enabled": False, "X": [1, 2], "Y": [8, 9]},
        {"Enabled": True, "X": [3, 4], "Y": [1, 7]},
    ]
    expected = [
        {"Enabled": True, "X": [4], "Y": [7]},
    ]
    assert_filtered(rows, ["Enabled", "Y > 5"], expected)

def test_none_cut_is_no_op():
    rows = [{"X": [1, 2], "Y": [3, 4]}]
    assert_filtered(rows, None, rows)

def test_blank_cut_is_ignored():
    rows = [{"X": [1, 2], "Y": [3, 4]}]
    assert_filtered(rows, "   ", rows)

def test_mismatched_vector_lengths_raise_on_evaluation():
    dataframe = make_dataframe([{
        "X": [1, 2, 3],
        "Y": [4, 5],
        "Z": [6, 7, 8],
    }])

    filtered = global_filter_cut_rdataframe(
        [dataframe],
        "X > 1 && Y > 1",
    )[0]

    try:
        materialize(filtered, ["X", "Y", "Z"])
    except Exception:
        # Expected: mismatched RVec lengths must fail evaluation.
        return

    raise AssertionError(
        "Expected vector-length mismatch to fail during evaluation."
    )

# ===========================================================================
# Additional high-complexity stress cases
# ===========================================================================


STRESS_CASES = [
    (
        "numeric_four_way_range",
        [{"A": [1,2,3,4,5], "B": [10,20,30,40,50], "C": [5,4,3,2,1], "D": [0,1,0,1,0]}],
        "(A >= 2 && A <= 5) && B >= 20 && C <= 4 && D == 1",
        [{"A": [2,4], "B": [20,40], "C": [4,2], "D": [1,1]}],
    ),
    (
        "numeric_arithmetic_cross_columns",
        [{"X": [1,2,3,4], "Y": [8,6,5,1], "Z": [2,2,2,2]}],
        "X * Z + Y >= 10",
        [{"X": [1,2,3], "Y": [8,6,5], "Z": [2,2,2]}],
    ),
    (
        "scalar_thresholds_with_vector",
        [
            {"Low": 25, "High": 80, "Energy": [10,30,50,90], "T": [1,2,3,4]},
            {"Low": 100, "High": 200, "Energy": [50,150,250], "T": [5,6,7]},
        ],
        "Energy >= Low && Energy < High",
        [
            {"Low": 25, "High": 80, "Energy": [30,50], "T": [2,3]},
            {"Low": 100, "High": 200, "Energy": [150], "T": [6]},
        ],
    ),
    (
        "bool_not_and_nested",
        [{"A": [True,False,True,False], "B": [False,False,True,True], "X": [1,2,3,4]}],
        "(!A && !B) || (A && B)",
        [{"A": [False,True], "B": [False,True], "X": [2,3]}],
    ),
    (
        "string_two_targets_or",
        [{"Name": ["muon","electron","proton","muon","gamma"], "E": [10,20,30,40,50]}],
        'Name == "muon" || Name == "proton"',
        [{"Name": ["muon","proton","muon"], "E": [10,30,40]}],
    ),
    (
        "string_not_equal_with_numeric",
        [{"Name": ["noise","muon","noise","proton"], "E": [100,20,300,400]}],
        'Name != "noise" && E >= 20',
        [{"Name": ["muon","proton"], "E": [20,400]}],
    ),
    (
        "scalar_string_gate_vector",
        [
            {"Mode": "Physics", "E": [10,60,100], "T": [1,2,3]},
            {"Mode": "Calibration", "E": [200,300], "T": [4,5]},
        ],
        'Mode == "Physics" && E > 50',
        [{"Mode": "Physics", "E": [60,100], "T": [2,3]}],
    ),
    (
        "multirow_string_vector_different_masks",
        [
            {"Name": ["a","target","b"], "E": [1,2,3]},
            {"Name": ["target","x","target"], "E": [10,20,30]},
        ],
        'Name == "target"',
        [
            {"Name": ["target"], "E": [2]},
            {"Name": ["target","target"], "E": [10,30]},
        ],
    ),
    (
        "cut_list_numeric",
        [{"X": [1,2,3,4,5], "Y": [5,4,3,2,1], "Good": [True,True,False,True,True]}],
        ["X >= 2", "Y <= 4", "Good", "X + Y == 6"],
        [{"X": [2,4,5], "Y": [4,2,1], "Good": [True,True,True]}],
    ),
    (
        "cut_list_string_bool",
        [{"Name": ["muon","proton","muon","electron"], "Good": [True,True,False,True], "E": [60,300,120,500]}],
        ['Name != "electron"', "Good || E > 250", "E >= 50"],
        [{"Name": ["muon","proton"], "Good": [True,True], "E": [60,300]}],
    ),
    (
        "scalar_force_or_vector",
        [
            {"Force": True, "X": [1,2,3], "E": [0,0,0]},
            {"Force": False, "X": [4,5,6], "E": [10,100,20]},
        ],
        "Force || E > 50",
        [
            {"Force": True, "X": [1,2,3], "E": [0,0,0]},
            {"Force": False, "X": [5], "E": [100]},
        ],
    ),
    (
        "deep_string_bool_combo",
        [{"Name": ["muon","electron","proton","muon"], "A": [True,False,True,False], "B": [False,True,True,True], "E": [10,200,300,90]}],
        '(Name == "muon" && (A || B) && E < 100) || (Name == "proton" && A && B)',
        [{"Name": ["muon","proton","muon"], "A": [True,True,False], "B": [False,True,True], "E": [10,300,90]}],
    ),
    (
        "negative_float_vectors",
        [{"X": [-3.5,-1.0,0.0,2.5,4.0], "Y": [1.0,2.0,3.0,4.0,5.0]}],
        "X < 0.0 || (X >= 2.0 && Y < 5.0)",
        [{"X": [-3.5,-1.0,2.5], "Y": [1.0,2.0,4.0]}],
    ),
    (
        "boolean_false_selection",
        [{"Good": [True,False,False,True], "X": [1,2,3,4]}],
        "!Good",
        [{"Good": [False,False], "X": [2,3]}],
    ),
    (
        "string_all_match",
        [{"Name": ["muon","muon","muon"], "X": [1,2,3]}],
        'Name == "muon"',
        [{"Name": ["muon","muon","muon"], "X": [1,2,3]}],
    ),
    (
        "string_no_match_reject_row",
        [{"Name": ["e","p","g"], "X": [1,2,3]}],
        'Name == "muon"',
        [],
    ),
    (
        "scalar_string_or_vector_condition",
        [
            {"Mode": "ForceAll", "X": [1,2,3], "E": [0,0,0]},
            {"Mode": "Physics", "X": [10,20,30], "E": [5,50,100]},
        ],
        'Mode == "ForceAll" || E >= 50',
        [
            {"Mode": "ForceAll", "X": [1,2,3], "E": [0,0,0]},
            {"Mode": "Physics", "X": [20,30], "E": [50,100]},
        ],
    ),
    (
        "many_aligned_vectors",
        [{"A": [1,2,3,4], "B": [10,20,30,40], "C": [100,200,300,400], "D": [True,False,True,True], "N": ["x","y","x","z"]}],
        'A >= 2 && C <= 400 && D && (N == "x" || N == "z")',
        [{"A": [3,4], "B": [30,40], "C": [300,400], "D": [True,True], "N": ["x","z"]}],
    ),
    (
        "string_column_prefixes",
        [{"Name": ["a","b","a"], "NameRaw": ["x","a","a"], "E": [1,2,3]}],
        'Name == "a" && NameRaw == "a"',
        [{"Name": ["a"], "NameRaw": ["a"], "E": [3]}],
    ),
    (
        "scalar_bool_changes_per_row_complex",
        [
            {"Enabled": True, "Force": False, "E": [10,60,70], "X": [1,2,3]},
            {"Enabled": False, "Force": True, "E": [10,20,30], "X": [4,5,6]},
            {"Enabled": False, "Force": False, "E": [100,200], "X": [7,8]},
        ],
        "(Enabled && E > 50) || Force",
        [
            {"Enabled": True, "Force": False, "E": [60,70], "X": [2,3]},
            {"Enabled": False, "Force": True, "E": [10,20,30], "X": [4,5,6]},
        ],
    ),
    (
        "bool_vector_two_string_targets",
        [{"Name": ["muon","electron","proton","muon"], "Good": [False,True,True,True], "E": [100,200,300,40]}],
        'Good && (Name == "muon" || Name == "proton") && E >= 40',
        [{"Name": ["proton","muon"], "Good": [True,True], "E": [300,40]}],
    ),
    (
        "threshold_scalar_bool_vector",
        [{"Threshold": 50, "Good": [True,False,True,True], "E": [40,60,80,50], "T": [1,2,3,4]}],
        "Good && E >= Threshold",
        [{"Threshold": 50, "Good": [True,True], "E": [80,50], "T": [3,4]}],
    ),
    (
        "nested_parentheses_string_numeric",
        [{"Name": ["a","b","c","a","b"], "X": [1,2,3,4,5], "Y": [5,4,3,2,1]}],
        '((Name == "a" && X > 2) || (Name == "b" && Y >= 4)) && X + Y == 6',
        [{"Name": ["b","a"], "X": [2,4], "Y": [4,2]}],
    ),
    (
        "vector_division_arithmetic",
        [{"X": [2.0,4.0,6.0,8.0], "Y": [1.0,2.0,4.0,2.0], "Good": [True,True,True,False]}],
        "Good && X / Y >= 2.0",
        [{"X": [2.0,4.0], "Y": [1.0,2.0], "Good": [True,True]}],
    ),
    (
        "combined_list_all_types",
        [{"Name": ["muon","proton","electron","muon","gamma"], "Good": [True,True,True,False,True], "E": [70,300,500,150,1000], "T": [1,2,3,4,5]}],
        ['Name != "gamma"', '(Name == "muon" || Name == "proton")', "Good || E > 400", "E >= 50", "T <= 4"],
        [{"Name": ["muon","proton"], "Good": [True,True], "E": [70,300], "T": [1,2]}],
    ),
]



# ===========================================================================
# 101-150: adversarial / weird regression cases
# ===========================================================================
#
# Focus:
#   - compound RVec<bool> expressions and nested negation
#   - bool-vector + scalar broadcasting
#   - string-vector rewrites mixed with bool/numeric masks
#   - identifier-prefix and string-literal collisions
#   - multiple-cut list interactions
#   - per-row scalar gates with vector masks
#   - aligned masking across bool/int/double/string vectors
#   - CharArray scalar-string gates combined with vector logic
# ===========================================================================

WEIRD_CASES = [('bool_xnor',
  [{'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  '(P && Q) || (!P && !Q)',
  [{'P': [True, False], 'Q': [True, False], 'X': [1, 4]}]),
 ('bool_xor',
  [{'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  '(P && !Q) || (!P && Q)',
  [{'P': [False, True], 'Q': [True, False], 'X': [2, 3]}]),
 ('bool_not_and_group',
  [{'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  '!(P && Q)',
  [{'P': [False, True, False], 'Q': [True, False, False], 'X': [2, 3, 4]}]),
 ('bool_not_or_group',
  [{'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  '!(P || Q)',
  [{'P': [False], 'Q': [False], 'X': [4]}]),
 ('bool_double_not',
  [{'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  '!!P',
  [{'P': [True, True], 'Q': [True, False], 'X': [1, 3]}]),
 ('bool_not_nested',
  [{'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  '!(!P || Q)',
  [{'P': [True], 'Q': [False], 'X': [3]}]),
 ('bool_tautology',
  [{'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  'P || !P',
  [{'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}]),
 ('bool_contradiction',
  [{'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  'P && !P',
  []),
 ('bool_reuse_same_column',
  [{'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  '(P && P) || (!P && !P)',
  [{'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}]),
 ('bool_equivalence_implication_form',
  [{'P': [True, False, True, False], 'Q': [True, True, False, False], 'X': [1, 2, 3, 4]}],
  '(P || !Q) && (!P || Q)',
  [{'P': [True, False], 'Q': [True, False], 'X': [1, 4]}]),
 ('bool_three_vector_majority',
  [{'P': [True, True, False, False],
    'Q': [True, False, True, False],
    'R': [False, True, True, False],
    'X': [1, 2, 3, 4]}],
  '(P && Q) || (P && R) || (Q && R)',
  [{'P': [True, True, False], 'Q': [True, False, True], 'R': [False, True, True], 'X': [1, 2, 3]}]),
 ('bool_three_vector_all_false_or_all_true',
  [{'P': [True, True, False, False],
    'Q': [True, False, True, False],
    'R': [False, True, True, False],
    'X': [1, 2, 3, 4]}],
  '(P && Q && R) || (!P && !Q && !R)',
  [{'P': [False], 'Q': [False], 'R': [False], 'X': [4]}]),
 ('bool_numeric_two_branches',
  [{'Good': [True, False, True, False], 'E': [0, 10, 20, 30], 'X': [1, 2, 3, 4]}],
  '(Good && E >= 20) || (!Good && E >= 30)',
  [{'Good': [True, False], 'E': [20, 30], 'X': [3, 4]}]),
 ('bool_numeric_not_group',
  [{'Good': [True, False, True, False], 'E': [0, 10, 20, 30], 'X': [1, 2, 3, 4]}],
  '!(Good && E < 25)',
  [{'Good': [False, False], 'E': [10, 30], 'X': [2, 4]}]),
 ('bool_numeric_double_not',
  [{'Good': [True, False, True, False], 'E': [0, 10, 20, 30], 'X': [1, 2, 3, 4]}],
  '!!Good && E >= 0',
  [{'Good': [True, True], 'E': [0, 20], 'X': [1, 3]}]),
 ('bool_numeric_nested',
  [{'Good': [True, False, True, False], 'E': [0, 10, 20, 30], 'X': [1, 2, 3, 4]}],
  '(Good && (E == 0 || E == 20)) || (!Good && E == 10)',
  [{'Good': [True, False, True], 'E': [0, 10, 20], 'X': [1, 2, 3]}]),
 ('scalar_true_and_bool_vector',
  [{'Enabled': True, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [10, 20, 30]},
   {'Enabled': False, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [40, 50, 60]}],
  'Enabled && Good',
  [{'Enabled': True, 'Good': [True, True], 'E': [1, 10], 'X': [10, 30]}]),
 ('scalar_not_or_bool_vector',
  [{'Enabled': True, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [10, 20, 30]},
   {'Enabled': False, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [40, 50, 60]}],
  '!Enabled || Good',
  [{'Enabled': True, 'Good': [True, True], 'E': [1, 10], 'X': [10, 30]},
   {'Enabled': False, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [40, 50, 60]}]),
 ('scalar_gate_two_bool_branches',
  [{'Enabled': True, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [10, 20, 30]},
   {'Enabled': False, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [40, 50, 60]}],
  '(Enabled && Good) || (!Enabled && !Good)',
  [{'Enabled': True, 'Good': [True, True], 'E': [1, 10], 'X': [10, 30]},
   {'Enabled': False, 'Good': [False], 'E': [5], 'X': [50]}]),
 ('scalar_gate_numeric_bool',
  [{'Enabled': True, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [10, 20, 30]},
   {'Enabled': False, 'Good': [True, False, True], 'E': [1, 5, 10], 'X': [40, 50, 60]}],
  '(Enabled && Good && E >= 5) || (!Enabled && E == 10)',
  [{'Enabled': True, 'Good': [True], 'E': [10], 'X': [30]},
   {'Enabled': False, 'Good': [True], 'E': [10], 'X': [60]}]),
 ('string_bool_same_literal_repeated',
  [{'Name': ['A', 'B', 'A', 'C'],
    'Flag': [True, False, True, False],
    'E': [10, 20, 30, 40],
    'X': [1, 2, 3, 4]}],
  'Flag && Name == "A"',
  [{'Name': ['A', 'A'], 'Flag': [True, True], 'E': [10, 30], 'X': [1, 3]}]),
 ('string_negated_bool',
  [{'Name': ['A', 'B', 'A', 'C'],
    'Flag': [True, False, True, False],
    'E': [10, 20, 30, 40],
    'X': [1, 2, 3, 4]}],
  '!Flag && Name != "A"',
  [{'Name': ['B', 'C'], 'Flag': [False, False], 'E': [20, 40], 'X': [2, 4]}]),
 ('string_bool_two_branches',
  [{'Name': ['A', 'B', 'A', 'C'],
    'Flag': [True, False, True, False],
    'E': [10, 20, 30, 40],
    'X': [1, 2, 3, 4]}],
  '(Flag && Name == "A") || (!Flag && Name == "C")',
  [{'Name': ['A', 'A', 'C'], 'Flag': [True, True, False], 'E': [10, 30, 40], 'X': [1, 3, 4]}]),
 ('string_group_negation',
  [{'Name': ['A', 'B', 'A', 'C'],
    'Flag': [True, False, True, False],
    'E': [10, 20, 30, 40],
    'X': [1, 2, 3, 4]}],
  '!(Flag && Name == "A")',
  [{'Name': ['B', 'C'], 'Flag': [False, False], 'E': [20, 40], 'X': [2, 4]}]),
 ('string_bool_numeric_nested',
  [{'Name': ['A', 'B', 'A', 'C'],
    'Flag': [True, False, True, False],
    'E': [10, 20, 30, 40],
    'X': [1, 2, 3, 4]}],
  '(Name == "A" && Flag && E >= 20) || (Name == "B" && !Flag)',
  [{'Name': ['B', 'A'], 'Flag': [False, True], 'E': [20, 30], 'X': [2, 3]}]),
 ('identifier_equals_string_literal',
  [{'A': [True, False, True, False],
    'Name': ['A', 'A', 'B', 'A'],
    'AA': [False, True, True, False],
    'X': [1, 2, 3, 4]}],
  'A && Name == "A"',
  [{'A': [True], 'Name': ['A'], 'AA': [False], 'X': [1]}]),
 ('identifier_prefix_A_AA',
  [{'A': [True, False, True, False],
    'Name': ['A', 'A', 'B', 'A'],
    'AA': [False, True, True, False],
    'X': [1, 2, 3, 4]}],
  'A && AA',
  [{'A': [True], 'Name': ['B'], 'AA': [True], 'X': [3]}]),
 ('identifier_prefix_negated',
  [{'A': [True, False, True, False],
    'Name': ['A', 'A', 'B', 'A'],
    'AA': [False, True, True, False],
    'X': [1, 2, 3, 4]}],
  '(!A && AA) || (A && !AA)',
  [{'A': [True, False], 'Name': ['A', 'A'], 'AA': [False, True], 'X': [1, 2]}]),
 ('prefix_E_Energy_EnergyRaw',
  [{'E': [1, 2, 3, 4], 'Energy': [4, 5, 6, 7], 'EnergyRaw': [7, 1, 9, 0], 'E1': [True, False, True, False]}],
  'Energy > 4 && EnergyRaw > 5',
  [{'E': [3], 'Energy': [6], 'EnergyRaw': [9], 'E1': [True]}]),
 ('prefix_bool_E1_with_E',
  [{'E': [1, 2, 3, 4], 'Energy': [4, 5, 6, 7], 'EnergyRaw': [7, 1, 9, 0], 'E1': [True, False, True, False]}],
  'E1 && E >= 2',
  [{'E': [3], 'Energy': [6], 'EnergyRaw': [9], 'E1': [True]}]),
 ('prefix_or_nested',
  [{'E': [1, 2, 3, 4], 'Energy': [4, 5, 6, 7], 'EnergyRaw': [7, 1, 9, 0], 'E1': [True, False, True, False]}],
  '(EnergyRaw > Energy) || (E1 && E == 1)',
  [{'E': [1, 3], 'Energy': [4, 6], 'EnergyRaw': [7, 9], 'E1': [True, True]}]),
 ('bool_prefix_Good_Good2',
  [{'Good': [True, False, True], 'Good2': [False, True, True], 'GoodRaw': [True, True, False], 'X': [1, 2, 3]}],
  'Good && Good2',
  [{'Good': [True], 'Good2': [True], 'GoodRaw': [False], 'X': [3]}]),
 ('bool_prefix_three_columns',
  [{'Good': [True, False, True], 'Good2': [False, True, True], 'GoodRaw': [True, True, False], 'X': [1, 2, 3]}],
  '(Good && !Good2) || (!Good && GoodRaw)',
  [{'Good': [True, False], 'Good2': [False, True], 'GoodRaw': [True, True], 'X': [1, 2]}]),
 ('bool_prefix_group_negation',
  [{'Good': [True, False, True], 'Good2': [False, True, True], 'GoodRaw': [True, True, False], 'X': [1, 2, 3]}],
  '!(Good && Good2) && GoodRaw',
  [{'Good': [True, False], 'Good2': [False, True], 'GoodRaw': [True, True], 'X': [1, 2]}]),
 ('cut_list_two_bool_vectors',
  [{'P': [True, False, True, False],
    'Q': [False, True, True, False],
    'E': [10, 20, 30, 40],
    'Name': ['muon', 'muon', 'proton', 'muon'],
    'X': [1, 2, 3, 4]}],
  ['P || Q', '(P && Q) || (!P && !Q)'],
  [{'P': [True], 'Q': [True], 'E': [30], 'Name': ['proton'], 'X': [3]}]),
 ('cut_list_bool_then_numeric',
  [{'P': [True, False, True, False],
    'Q': [False, True, True, False],
    'E': [10, 20, 30, 40],
    'Name': ['muon', 'muon', 'proton', 'muon'],
    'X': [1, 2, 3, 4]}],
  ['P || Q', 'E >= 20'],
  [{'P': [False, True], 'Q': [True, True], 'E': [20, 30], 'Name': ['muon', 'proton'], 'X': [2, 3]}]),
 ('cut_list_string_bool_numeric',
  [{'P': [True, False, True, False],
    'Q': [False, True, True, False],
    'E': [10, 20, 30, 40],
    'Name': ['muon', 'muon', 'proton', 'muon'],
    'X': [1, 2, 3, 4]}],
  ['Name == "muon"', '!Q || P', 'E >= 10'],
  [{'P': [True, False],
    'Q': [False, False],
    'E': [10, 40],
    'Name': ['muon', 'muon'],
    'X': [1, 4]}]),
 ('cut_list_repeated_same_cut',
  [{'P': [True, False, True, False],
    'Q': [False, True, True, False],
    'E': [10, 20, 30, 40],
    'Name': ['muon', 'muon', 'proton', 'muon'],
    'X': [1, 2, 3, 4]}],
  ['P', 'P', 'P'],
  [{'P': [True, True], 'Q': [False, True], 'E': [10, 30], 'Name': ['muon', 'proton'], 'X': [1, 3]}]),
 ('cut_list_negated_then_or',
  [{'P': [True, False, True, False],
    'Q': [False, True, True, False],
    'E': [10, 20, 30, 40],
    'Name': ['muon', 'muon', 'proton', 'muon'],
    'X': [1, 2, 3, 4]}],
  ['!P || Q', 'Q || E >= 40'],
  [
    {
        "P": [False, True, False],
        "Q": [True, True, False],
        "E": [20, 30, 40],
        "Name": ["muon", "proton", "muon"],
        "X": [2, 3, 4],
    }
]),
 ('cut_list_parenthesized_compound',
  [{'P': [True, False, True, False],
    'Q': [False, True, True, False],
    'E': [10, 20, 30, 40],
    'Name': ['muon', 'muon', 'proton', 'muon'],
    'X': [1, 2, 3, 4]}],
  ['(P || Q)', '((E >= 20 && E <= 40))', '(Name != "electron")'],
  [
    {
        "P": [False, True],
        "Q": [True, True],
        "E": [20, 30],
        "Name": ["muon", "proton"],
        "X": [2, 3],
    }
]),
 ('multirow_bool_distinct_masks',
  [{'Gate': True, 'P': [True, False, True], 'Q': [False, False, True], 'X': [1, 2, 3]},
   {'Gate': False, 'P': [False, True, False], 'Q': [False, True, True], 'X': [4, 5, 6]}],
  '(P && Q) || (!P && !Q)',
  [{'Gate': True, 'P': [False, True], 'Q': [False, True], 'X': [2, 3]},
   {'Gate': False, 'P': [False, True], 'Q': [False, True], 'X': [4, 5]}]),
 ('multirow_scalar_gate_and_vector',
  [{'Gate': True, 'P': [True, False, True], 'Q': [False, False, True], 'X': [1, 2, 3]},
   {'Gate': False, 'P': [False, True, False], 'Q': [False, True, True], 'X': [4, 5, 6]}],
  'Gate && (P || Q)',
  [{'Gate': True, 'P': [True, True], 'Q': [False, True], 'X': [1, 3]}]),
 ('multirow_scalar_force_or_vector',
  [{'Gate': True, 'P': [True, False, True], 'Q': [False, False, True], 'X': [1, 2, 3]},
   {'Gate': False, 'P': [False, True, False], 'Q': [False, True, True], 'X': [4, 5, 6]}],
  '!Gate || (P && Q)',
  [{'Gate': True, 'P': [True], 'Q': [True], 'X': [3]},
   {'Gate': False, 'P': [False, True, False], 'Q': [False, True, True], 'X': [4, 5, 6]}]),
 ('multirow_scalar_string_and_bool_vector',
  [{'Mode': 'Physics', 'P': [True, False, True], 'E': [10, 20, 30], 'X': [1, 2, 3]},
   {'Mode': 'Calibration', 'P': [False, False, True], 'E': [100, 200, 300], 'X': [4, 5, 6]}],
  'Mode == "Physics" && P',
  [{'Mode': 'Physics', 'P': [True, True], 'E': [10, 30], 'X': [1, 3]}]),
 ('multirow_scalar_string_or_numeric_vector',
  [{'Mode': 'Physics', 'P': [True, False, True], 'E': [10, 20, 30], 'X': [1, 2, 3]},
   {'Mode': 'Calibration', 'P': [False, False, True], 'E': [100, 200, 300], 'X': [4, 5, 6]}],
  'Mode == "Calibration" || E >= 20',
  [{'Mode': 'Physics', 'P': [False, True], 'E': [20, 30], 'X': [2, 3]},
   {'Mode': 'Calibration', 'P': [False, False, True], 'E': [100, 200, 300], 'X': [4, 5, 6]}]),
 ('mask_mixed_vector_types_xnor',
  [{'P': [True, False, True, False],
    'Q': [False, True, True, False],
    'I': [10, 20, 30, 40],
    'D': [1.5, 2.5, 3.5, 4.5],
    'S': ['a', 'b', 'c', 'd'],
    'X': [100, 200, 300, 400]}],
  '(P && Q) || (!P && !Q)',
  [{'P': [True, False], 'Q': [True, False], 'I': [30, 40], 'D': [3.5, 4.5], 'S': ['c', 'd'], 'X': [300, 400]}]),
 ('mask_mixed_vector_types_xor',
  [{'P': [True, False, True, False],
    'Q': [False, True, True, False],
    'I': [10, 20, 30, 40],
    'D': [1.5, 2.5, 3.5, 4.5],
    'S': ['a', 'b', 'c', 'd'],
    'X': [100, 200, 300, 400]}],
  '(P && !Q) || (!P && Q)',
  [{'P': [True, False], 'Q': [False, True], 'I': [10, 20], 'D': [1.5, 2.5], 'S': ['a', 'b'], 'X': [100, 200]}]),
 ('all_false_bool_xnor',
  [{'P': [False, False, False], 'Q': [False, False, False], 'X': [1, 2, 3]}],
  '(P && Q) || (!P && !Q)',
  [{'P': [False, False, False], 'Q': [False, False, False], 'X': [1, 2, 3]}]),
 ('single_element_compound_bool',
  [{'P': [False], 'Q': [False], 'Name': ['x'], 'X': [99]}],
  '(P && Q) || (!P && !Q)',
  [{'P': [False], 'Q': [False], 'Name': ['x'], 'X': [99]}]),
 ('escaped_scalar_string_gate_with_bool_vectors',
  [{'Mode': 'Det"A', 'P': [True, False, True], 'Q': [False, False, True], 'X': [1, 2, 3]}],
  'Mode == "Det\\\"A" && ((P && Q) || (!P && !Q))',
  [{'Mode': 'Det"A', 'P': [False, True], 'Q': [False, True], 'X': [2, 3]}])]


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
        cut,
        expected,
    ) in cases:

        def run(
            rows=rows,
            cut=cut,
            expected=expected,
        ):
            check_filter(
                rows,
                cut,
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

    # Current 28-test suite.
    tests.extend(_case_tests("scalar", SCALAR_CASES))
    tests.extend(_case_tests("vector", VECTOR_CASES))
    tests.extend(_case_tests("bool_vector", BOOL_VECTOR_CASES))
    tests.extend(_case_tests("string_vector", STRING_VECTOR_CASES))
    tests.extend(_case_tests("mixed", MIXED_CASES))

    current_standalone = [
        test_char_array_equal,
        test_char_array_not_equal,
        test_char_array_bool_numeric,
        test_everything_mixed,
        test_deep_nested_everything,
        test_multiple_cut_list_everything,
        test_no_vector_element_survives,
        test_single_dataframe_returns_single_dataframe,
        test_dataframe_list_returns_list,
        test_none_is_noop,
        test_blank_is_noop,
        test_mismatched_vector_lengths_fail,
    ]

    tests.extend(
        (test.__name__, test)
        for test in current_standalone
    )

    # Earlier 47-test regression suite.
    tests.extend(_case_tests("previous_scalar", PREVIOUS_SCALAR_CASES))
    tests.extend(_case_tests("previous_vector", PREVIOUS_VECTOR_CASES))
    tests.extend(_case_tests("previous_mixed", PREVIOUS_MIXED_CASES))

    previous_standalone = [
        test_multiple_dataframes_are_filtered_independently,
        test_three_mixed_dataframes_one_cut,
        test_chained_vector_cuts_apply_sequentially,
        test_chained_scalar_then_vector_cut,
        test_none_cut_is_no_op,
        test_blank_cut_is_ignored,
        test_mismatched_vector_lengths_raise_on_evaluation,
    ]

    tests.extend(
        (f"previous.{test.__name__}", test)
        for test in previous_standalone
    )

    # 25 new high-complexity tests.
    tests.extend(_case_tests("stress", STRESS_CASES))

    # 50 additional adversarial regression tests.
    tests.extend(_case_tests("weird", WEIRD_CASES))

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
        "global_filter_cut_rdataframe tests...\n"
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