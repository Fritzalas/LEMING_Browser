"""

Exactly 160 standalone stress tests for detector_event_filter_cut_rdataframe.

Focus:

  * deterministic random row shuffling in every semantic test

  * non-adjacent rows belonging to the same (RunNumber, SubrunNumber, IEventNb)

  * implicit-multithreaded ROOT.RDataFrame execution

  * duplicate requested-detector rows: ALL must pass

  * missing requested detectors reject the complete event

  * unrelated detector rows are preserved when the event passes

  * reused IEventNb values across different runs/subruns

  * scalar, boolean and RVec-valued cuts (RVec uses VecOps::All semantics)

  * RVec<Char_t> detector names

  * multiple RDataFrames and repeated calls

  * bounded stress dataframes, including one final 1000-row stress test

  * API/error boundaries including 64 detector mask limit

Run:

    python test_detector_event_filter_cut_rdataframe_standalone.py

"""

from __future__ import annotations

from collections import defaultdict

from typing import Any, Callable

import importlib

import math

import os

import random

import sys

import time

import ROOT





# ===========================================================================

# Import function under test

# ===========================================================================

current = os.path.dirname(os.path.realpath(__file__))

parent = os.path.dirname(current)

if parent not in sys.path:

    sys.path.append(parent)

from Helpers.Filter.detector_event_filter_cut_rdataframe import detector_event_filter_cut_rdataframe

# ===========================================================================

# Force an IMT execution environment

# ===========================================================================

try:

    already_mt = (

        ROOT.IsImplicitMTEnabled()

        if hasattr(ROOT, "IsImplicitMTEnabled")

        else False

    )

    if not already_mt:

        ROOT.EnableImplicitMT(4)

except Exception:

    pass





# ===========================================================================

# ROOT test-data builder

# ===========================================================================

class CharArray:

    def __init__(self, value: str):

        self.value = value





def _escape_cpp_string(value: str) -> str:
    """Escape a Python string for safe use inside a C++ string literal."""
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





def _infer_vector_cpp_type(rows: list[list[Any]]) -> str:

    flat = [value for row in rows for value in row]

    if not flat:

        return "int"

    if all(isinstance(value, bool) for value in flat):

        return "bool"

    if all(isinstance(value, str) for value in flat):

        return "std::string"

    if any(isinstance(value, float) for value in flat):

        return "double"

    return "int"





def _cpp_vector(values: list[Any], cpp_type: str) -> str:

    return (

        f"ROOT::VecOps::RVec<{cpp_type}>{{"

        + ", ".join(_cpp_scalar(value) for value in values)

        + "}"

    )





def _cpp_char_array(value: str) -> str:

    values = [str(byte) for byte in value.encode("utf-8")]

    values.append("0")

    return "ROOT::VecOps::RVec<Char_t>{" + ", ".join(values) + "}"





def _column_expression(values: list[Any]) -> str:

    first = values[0]

    if isinstance(first, CharArray):

        literals = [_cpp_char_array(value.value) for value in values]

        fallback = "ROOT::VecOps::RVec<Char_t>{0}"

    elif isinstance(first, (list, tuple)):

        rows = [list(value) for value in values]

        cpp_type = _infer_vector_cpp_type(rows)

        literals = [_cpp_vector(row, cpp_type) for row in rows]

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

    # Build a BALANCED decision tree instead of one deeply nested

    # right-associative ternary chain.

    #

    # Old shape for N rows:

    #     entry == 0 ? v0 : (entry == 1 ? v1 : (...))

    #

    # has O(N) C++ bracket nesting and makes Cling fail around

    # its default nesting limit for large stress dataframes.

    #

    # This tree has O(log N) nesting, so large stress inputs are safe.

    def build_tree(lo: int, hi: int) -> str:

        if lo >= hi:

            return fallback

        if hi - lo == 1:

            return (

                f"(rdfentry_ == {lo}ULL ? "

                f"{literals[lo]} : {fallback})"

            )

        mid = (lo + hi) // 2

        left = build_tree(

            lo,

            mid,

        )

        right = build_tree(

            mid,

            hi,

        )

        return (

            f"(rdfentry_ < {mid}ULL ? "

            f"{left} : {right})"

        )

    return build_tree(

        0,

        len(literals),

    )





def make_dataframe(rows: list[dict[str, Any]]):

    assert rows

    columns = list(rows[0])

    assert all(list(row) == columns for row in rows)

    dataframe = ROOT.RDataFrame(len(rows))

    for column in columns:

        dataframe = dataframe.Define(

            column,

            _column_expression([row[column] for row in rows]),

        )

    return dataframe





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





def materialize(dataframe, columns: list[str]) -> list[dict[str, Any]]:

    arrays = dataframe.AsNumpy(columns)

    count = len(arrays[columns[0]])

    return [

        {

            column: _python_value(arrays[column][row])

            for column in columns

        }

        for row in range(count)

    ]





# ===========================================================================

# Independent Python oracle

# ===========================================================================

def key(row):

    return (

        int(row["RunNumber"]),

        int(row["SubrunNumber"]),

        int(row["IEventNb"]),

    )





def detector_text(value):

    return value.value if isinstance(value, CharArray) else str(value)





def shuffled(rows, seed):

    result = list(rows)

    random.Random(seed).shuffle(result)

    return result





def _norm(value):

    if isinstance(value, list):

        return tuple(_norm(item) for item in value)

    return value





def canonical(rows, columns):

    return sorted(

        rows,

        key=lambda row: tuple(repr(_norm(row[c])) for c in columns),

    )





def oracle(

    rows: list[dict[str, Any]],

    detectors: list[str],

    passes: Callable[[dict[str, Any], str], bool],

    detector_column: str = "Detector",

):

    groups = defaultdict(list)

    for row in rows:

        groups[key(row)].append(row)

    accepted = set()

    for event_key, group in groups.items():

        event_ok = True

        for detector in detectors:

            matching = [

                row

                for row in group

                if detector_text(row[detector_column]) == detector

            ]

            if not matching or not all(passes(row, detector) for row in matching):

                event_ok = False

                break

        if event_ok:

            accepted.add(event_key)

    return [row for row in rows if key(row) in accepted]





def check(

    rows,

    detectors,

    cuts,

    expected,

    *,

    seed,

    detector_column="Detector",

    columns=None,

):

    input_rows = shuffled(rows, seed)

    t0 = time.perf_counter()

    dataframe = make_dataframe(input_rows)

    t1 = time.perf_counter()

    result = detector_event_filter_cut_rdataframe(

        dataframe,

        detectors,

        cuts,

        detector_column,

        "IEventNb",

        "RunNumber",

        "SubrunNumber",

    )

    if columns is None:

        columns = list(rows[0])

    t2 = time.perf_counter()

    actual = canonical(materialize(result, columns), columns)

    t3 = time.perf_counter()

    print(

        f"dataframe build: {t1 - t0:.3f}s | "

        f"filter first pass/setup: {t2 - t1:.3f}s | "

        f"second pass/materialize: {t3 - t2:.3f}s"

    )

    projected = []

    for row in expected:

        projected.append({

            column: (

                row[column].value

                if isinstance(row[column], CharArray)

                else row[column]

            )

            for column in columns

        })

    projected = canonical(projected, columns)

    assert actual == projected, (

        f"\nDetectors: {detectors}\n"

        f"Cuts: {cuts}\n"

        f"Expected ({len(projected)} rows): {projected[:20]}\n"

        f"Actual   ({len(actual)} rows): {actual[:20]}"

    )





# ===========================================================================

# Common row factory

# ===========================================================================

def scalar_row(run, subrun, event, detector, energy, time_value, good, payload):

    return {

        "RunNumber": run,

        "SubrunNumber": subrun,

        "IEventNb": event,

        "Detector": detector,

        "Energy": float(energy),

        "Time": float(time_value),

        "Good": bool(good),

        "Payload": int(payload),

    }





# ===========================================================================

# Generated tests: 120 total

# ===========================================================================

GENERATED = []





def add_generated(name, fn):

    GENERATED.append((f"test_{name}", fn))





# 1-30: randomized scalar groups, duplicates, missing detectors, noise rows.

for case in range(30):

    def test(case=case):

        rng = random.Random(10000 + case)

        rows = []

        # Keys are unique triples, while IEventNb intentionally repeats.

        for g in range(35 + case):

            run = 1 + g // 18

            subrun = 10 + (g // 9) % 2

            event = g % 9

            for detector in ("A", "B", "C"):

                copies = 1 + rng.randrange(3)

                if detector == "C" and g % 13 == case % 13:

                    copies = 0

                for copy_index in range(copies):

                    rows.append(

                        scalar_row(

                            run,

                            subrun,

                            event,

                            detector,

                            20 + rng.randrange(130),

                            rng.randrange(200),

                            rng.random() > 0.10,

                            case * 1_000_000 + g * 100 + copy_index,

                        )

                    )

            for noise in range(rng.randrange(4)):

                rows.append(

                    scalar_row(

                        run,

                        subrun,

                        event,

                        f"Noise{noise}",

                        -999,

                        9999,

                        False,

                        case * 1_000_000 + g * 100 + 90 + noise,

                    )

                )

        detectors = ["A", "B", "C"]

        cuts = [

            "Energy >= 35 && Good",

            "Energy < 125 && Good",

            "Time < 170 && Good",

        ]

        def passes(row, detector):

            if detector == "A":

                return row["Energy"] >= 35 and row["Good"]

            if detector == "B":

                return row["Energy"] < 125 and row["Good"]

            return row["Time"] < 170 and row["Good"]

        expected = oracle(rows, detectors, passes)

        check(

            rows,

            detectors,

            cuts,

            expected,

            seed=20000 + case,

        )

    add_generated(f"random_scalar_groups_{case:02d}", test)





# 31-50: one failing duplicate must reject all rows of that event.

for case in range(20):

    def test(case=case):

        rows = []

        for event in range(50):

            run = 20 + event // 25

            subrun = 5 + (event // 10) % 2

            local_event = event % 10

            values = [

                ("A", 100, 10, True),

                ("A", 120, 11, True),

                ("B", 100, 20, True),

                ("B", 100, 21, True),

            ]

            if (event + case) % 7 == 0:

                values[1] = ("A", -1, 11, True)

            if (event + case) % 11 == 0:

                values[3] = ("B", 100, 999, True)

            for index, (detector, energy, t, good) in enumerate(values):

                rows.append(

                    scalar_row(

                        run, subrun, local_event,

                        detector, energy, t, good,

                        case * 100000 + event * 10 + index,

                    )

                )

            rows.append(

                scalar_row(

                    run, subrun, local_event,

                    "Unrelated", -5000, 5000, False,

                    case * 100000 + event * 10 + 9,

                )

            )

        detectors = ["A", "B"]

        cuts = ["Energy > 0", "Time < 100"]

        expected = oracle(

            rows,

            detectors,

            lambda row, detector: (

                row["Energy"] > 0

                if detector == "A"

                else row["Time"] < 100

            ),

        )

        check(rows, detectors, cuts, expected, seed=30000 + case)

    add_generated(f"duplicate_detector_rows_{case:02d}", test)





# 51-70: vector-valued cuts; CutPass must require VecOps::All.

for case in range(20):

    def test(case=case):

        rows = []

        for g in range(30):

            run = 30 + g // 15

            subrun = 7 + (g // 5) % 3

            event = g % 5

            shift = g + case

            a_energy = [60.0, 70.0, 80.0]

            if shift % 7 == 0:

                a_energy[2] = 10.0

            a_good = [True, True, shift % 9 != 0]

            b_energy = [10.0, 20.0, 30.0]

            if shift % 8 == 0:

                b_energy[1] = 500.0

            rows.extend([

                {

                    "RunNumber": run, "SubrunNumber": subrun, "IEventNb": event,

                    "Detector": "A",

                    "EnergyVec": a_energy,

                    "GoodVec": a_good,

                    "Payload": case * 10000 + g * 10 + 1,

                },

                {

                    "RunNumber": run, "SubrunNumber": subrun, "IEventNb": event,

                    "Detector": "B",

                    "EnergyVec": b_energy,

                    "GoodVec": [True, True, True],

                    "Payload": case * 10000 + g * 10 + 2,

                },

                {

                    "RunNumber": run, "SubrunNumber": subrun, "IEventNb": event,

                    "Detector": "Noise",

                    "EnergyVec": [9999.0],

                    "GoodVec": [False],

                    "Payload": case * 10000 + g * 10 + 3,

                },

            ])

        detectors = ["A", "B"]

        cuts = [

            "EnergyVec > 50 && GoodVec",

            "EnergyVec < 100",

        ]

        def passes(row, detector):

            if detector == "A":

                return all(

                    energy > 50 and good

                    for energy, good in zip(row["EnergyVec"], row["GoodVec"])

                )

            return all(energy < 100 for energy in row["EnergyVec"])

        expected = oracle(rows, detectors, passes)

        check(rows, detectors, cuts, expected, seed=40000 + case)

    add_generated(f"vector_all_semantics_{case:02d}", test)





# 71-85: missing requested detector among many irrelevant rows.

for case in range(15):

    def test(case=case):

        rows = []

        for g in range(60):

            run = 40 + g // 20

            subrun = 3 + (g // 10) % 2

            event = g % 10

            present = ["A", "B", "C"]

            missing_selector = (g + case) % 12

            if missing_selector < 3:

                present.remove(("A", "B", "C")[missing_selector])

            for index, detector in enumerate(present):

                rows.append(

                    scalar_row(

                        run, subrun, event,

                        detector, 100, 1, True,

                        case * 100000 + g * 100 + index,

                    )

                )

            for extra in range(8):

                rows.append(

                    scalar_row(

                        run, subrun, event,

                        f"Extra{extra}", -999, 999, False,

                        case * 100000 + g * 100 + 20 + extra,

                    )

                )

        detectors = ["A", "B", "C"]

        cuts = ["Energy > 0", "Energy > 0", "Energy > 0"]

        expected = oracle(

            rows,

            detectors,

            lambda row, detector: row["Energy"] > 0,

        )

        check(rows, detectors, cuts, expected, seed=50000 + case)

    add_generated(f"missing_detector_{case:02d}", test)





# 86-100: full triple key, same event number across run/subrun.

for case in range(15):

    def test(case=case):

        rows = []

        for run_offset in range(4):

            for subrun_offset in range(5):

                for event in range(6):

                    fail = (

                        run_offset * 100

                        + subrun_offset * 10

                        + event

                        + case

                    ) % 9 == 0

                    run = 100 + run_offset

                    subrun = 200 + subrun_offset

                    rows.extend([

                        scalar_row(

                            run, subrun, event,

                            "A", -1 if fail else 100, 1, True,

                            case * 1000000 + run_offset * 10000

                            + subrun_offset * 1000 + event * 10 + 1,

                        ),

                        scalar_row(

                            run, subrun, event,

                            "B", 100, 1, True,

                            case * 1000000 + run_offset * 10000

                            + subrun_offset * 1000 + event * 10 + 2,

                        ),

                    ])

        detectors = ["A", "B"]

        cuts = ["Energy > 0", "Energy > 0"]

        expected = oracle(

            rows,

            detectors,

            lambda row, detector: row["Energy"] > 0,

        )

        check(rows, detectors, cuts, expected, seed=60000 + case)

    add_generated(f"full_event_key_{case:02d}", test)





# 101-110: RVec<Char_t> detector names.

for case in range(10):

    def test(case=case):

        rows = []

        for event in range(40):

            fail = (event + case) % 6 == 0

            for detector, energy, payload_offset in [

                ("A", 0 if fail else 100, 1),

                ("B", 50, 2),

                ("Other", -999, 3),

            ]:

                rows.append({

                    "RunNumber": 500 + event // 20,

                    "SubrunNumber": 600 + (event // 10) % 2,

                    "IEventNb": event % 10,

                    "DetectorChar": CharArray(detector),

                    "Energy": float(energy),

                    "Payload": case * 10000 + event * 10 + payload_offset,

                })

        detectors = ["A", "B"]

        cuts = ["Energy > 10", "Energy > 10"]

        expected = oracle(

            rows,

            detectors,

            lambda row, detector: row["Energy"] > 10,

            detector_column="DetectorChar",

        )

        check(

            rows,

            detectors,

            cuts,

            expected,

            detector_column="DetectorChar",

            columns=[

                "RunNumber", "SubrunNumber", "IEventNb",

                "Energy", "Payload",

            ],

            seed=70000 + case,

        )

    add_generated(f"char_array_detector_{case:02d}", test)





# 111-120: nested mixed scalar/RVec expressions.

for case in range(10):

    def test(case=case):

        rows = []

        for g in range(40):

            run = 700 + g // 20

            subrun = 800 + (g // 10) % 2

            event = g % 10

            shift = g + case

            rows.extend([

                {

                    "RunNumber": run, "SubrunNumber": subrun, "IEventNb": event,

                    "Detector": "A",

                    "Enabled": True,

                    "Threshold": 50.0,

                    "EnergyVec": [60.0, 20.0 if shift % 5 == 0 else 90.0],

                    "GoodVec": [True, True],

                    "Payload": case * 100000 + g * 10 + 1,

                },

                {

                    "RunNumber": run, "SubrunNumber": subrun, "IEventNb": event,

                    "Detector": "B",

                    "Enabled": shift % 7 != 0,

                    "Threshold": 100.0,

                    "EnergyVec": [10.0, 150.0 if shift % 6 == 0 else 20.0],

                    "GoodVec": [True, True],

                    "Payload": case * 100000 + g * 10 + 2,

                },

                {

                    "RunNumber": run, "SubrunNumber": subrun, "IEventNb": event,

                    "Detector": "Noise",

                    "Enabled": False,

                    "Threshold": 0.0,

                    "EnergyVec": [9999.0],

                    "GoodVec": [False],

                    "Payload": case * 100000 + g * 10 + 3,

                },

            ])

        detectors = ["A", "B"]

        cuts = [

            "Enabled && EnergyVec >= Threshold && GoodVec",

            "Enabled && (EnergyVec < Threshold || EnergyVec == 150)",

        ]

        def passes(row, detector):

            if detector == "A":

                return (

                    row["Enabled"]

                    and all(

                        energy >= row["Threshold"] and good

                        for energy, good in zip(

                            row["EnergyVec"],

                            row["GoodVec"],

                        )

                    )

                )

            return (

                row["Enabled"]

                and all(

                    energy < row["Threshold"] or energy == 150

                    for energy in row["EnergyVec"]

                )

            )

        expected = oracle(rows, detectors, passes)

        check(rows, detectors, cuts, expected, seed=80000 + case)

    add_generated(f"nested_vector_scalar_{case:02d}", test)





assert len(GENERATED) == 120





# ===========================================================================

# 30 explicit edge / bounded-stress / API tests

# ===========================================================================

def test_stress_shuffled_mixed_failures_240_rows():

    """240 rows: shuffled groups, 3 requested detectors, noise, mixed failures."""

    rows = []

    for event in range(60):  # 60 * 4 = 240 rows

        run = 1000 + event % 7

        subrun = 2000 + event % 11

        for detector, energy, t, good, offset in [

            ("A", -1 if event % 17 == 0 else 100, 1, True, 1),

            ("B", 100, 999 if event % 19 == 0 else 2, True, 2),

            ("C", 100, 3, event % 23 != 0, 3),

            ("Noise", -999, 9999, False, 4),

        ]:

            rows.append(

                scalar_row(

                    run, subrun, event,

                    detector, energy, t, good,

                    event * 10 + offset,

                )

            )

    detectors = ["A", "B", "C"]

    cuts = ["Energy > 0", "Time < 100", "Good"]

    expected = oracle(

        rows,

        detectors,

        lambda row, detector: (

            row["Energy"] > 0 if detector == "A"

            else row["Time"] < 100 if detector == "B"

            else row["Good"]

        ),

    )

    check(rows, detectors, cuts, expected, seed=91001)



def test_stress_reused_event_numbers_240_rows():

    """240 rows: reused event IDs across run/subrun keys plus unrelated rows."""

    rows = []

    for group in range(80):  # 80 * 3 = 240 rows

        run = 3000 + group % 5

        subrun = 4000 + (group // 5) % 4

        event = group % 10  # deliberately reused

        rows.extend([

            scalar_row(

                run, subrun, event,

                "A",

                -1 if group % 13 == 0 else 100,

                1,

                True,

                group * 10 + 1,

            ),

            scalar_row(

                run, subrun, event,

                "B",

                100,

                1,

                group % 17 != 0,

                group * 10 + 2,

            ),

            scalar_row(

                run, subrun, event,

                "Other",

                -999,

                999,

                False,

                group * 10 + 3,

            ),

        ])

    detectors = ["A", "B"]

    cuts = ["Energy > 10", "Good"]

    expected = oracle(

        rows,

        detectors,

        lambda row, detector: (

            row["Energy"] > 10 if detector == "A"

            else row["Good"]

        ),

    )

    check(rows, detectors, cuts, expected, seed=91002)



def test_stress_many_duplicates_270_rows():

    """270 rows: many duplicate detector rows; one bad duplicate rejects event."""

    rows = []

    for event in range(15):

        for copy in range(10):

            rows.append(

                scalar_row(

                    7, event % 5, event,

                    "A",

                    -1 if event % 7 == 0 and copy == 9 else 100,

                    copy,

                    True,

                    event * 100 + copy,

                )

            )

        for copy in range(8):

            rows.append(

                scalar_row(

                    7, event % 5, event,

                    "B",

                    100,

                    copy,

                    not (event % 11 == 0 and copy == 7),

                    event * 100 + 50 + copy,

                )

            )

    assert len(rows) == 270

    detectors = ["A", "B"]

    cuts = ["Energy > 0", "Good"]

    expected = oracle(

        rows,

        detectors,

        lambda row, detector: (

            row["Energy"] > 0 if detector == "A"

            else row["Good"]

        ),

    )

    check(rows, detectors, cuts, expected, seed=91003)



def test_single_dataframe_returns_single():

    rows = [

        scalar_row(1, 1, 1, "A", 10, 1, True, 1),

        scalar_row(1, 1, 1, "B", 10, 1, True, 2),

    ]

    result = detector_event_filter_cut_rdataframe(

        make_dataframe(shuffled(rows, 92001)),

        ["A", "B"],

        ["Energy > 0", "Energy > 0"],

        "Detector",

        "IEventNb",

        "RunNumber",

        "SubrunNumber",

    )

    assert not isinstance(result, list)



def test_dataframe_list_returns_list():

    passing = [

        scalar_row(1, 1, 1, "A", 10, 1, True, 1),

        scalar_row(1, 1, 1, "B", 10, 1, True, 2),

    ]

    failing = [

        scalar_row(2, 2, 2, "A", -1, 1, True, 3),

        scalar_row(2, 2, 2, "B", 10, 1, True, 4),

    ]

    results = detector_event_filter_cut_rdataframe(

        [

            make_dataframe(shuffled(passing, 92002)),

            make_dataframe(shuffled(failing, 92003)),

        ],

        ["A", "B"],

        ["Energy > 0", "Energy > 0"],

        "Detector",

           "IEventNb",

        "RunNumber",

        "SubrunNumber",

    )

    assert isinstance(results, list)

    assert len(results) == 2

    assert len(materialize(results[0], ["Payload"])) == 2

    assert materialize(results[1], ["Payload"]) == []





def test_three_dataframes_independent():

    dataframes = []

    expected_counts = []

    for dataset in range(3):

        rows = []

        for event in range(200):

            fail = event % (11 + dataset) == 0

            rows.extend([

                scalar_row(dataset, 1, event, "A", -1 if fail else 10, 1, True, event * 10 + 1),

                scalar_row(dataset, 1, event, "B", 10, 1, True, event * 10 + 2),

            ])

        expected = oracle(rows, ["A", "B"], lambda row, detector: row["Energy"] > 0)

        expected_counts.append(len(expected))

        dataframes.append(make_dataframe(shuffled(rows, 92010 + dataset)))

    results = detector_event_filter_cut_rdataframe(

        dataframes,

        ["A", "B"],

        ["Energy > 0", "Energy > 0"],

        "Detector",

           "IEventNb",

        "RunNumber",

        "SubrunNumber",

    )

    assert [

        len(materialize(result, ["Payload"]))

        for result in results

    ] == expected_counts





def test_unrelated_failure_does_not_matter():

    rows = [

        scalar_row(1, 1, 1, "A", 100, 1, True, 1),

        scalar_row(1, 1, 1, "B", 100, 1, True, 2),

        scalar_row(1, 1, 1, "Noise", -99999, 99999, False, 3),

    ]

    check(

        rows,

        ["A", "B"],

        ["Energy > 0 && Good", "Energy > 0 && Good"],

        rows,

        seed=92020,

    )





def test_missing_one_detector_rejects():

    rows = [

        scalar_row(1, 1, 1, "A", 100, 1, True, 1),

        scalar_row(1, 1, 1, "Noise", 100, 1, True, 2),

    ]

    check(rows, ["A", "B"], ["Energy > 0", "Energy > 0"], [], seed=92021)





def test_all_requested_detectors_missing():

    rows = [scalar_row(1, 1, 1, "Noise", 100, 1, True, 1)]

    check(rows, ["A", "B"], ["Energy > 0", "Energy > 0"], [], seed=92022)





def test_one_bad_duplicate_rejects():

    rows = [

        scalar_row(1, 1, 1, "A", 100, 1, True, 1),

        scalar_row(1, 1, 1, "A", -1, 1, True, 2),

        scalar_row(1, 1, 1, "B", 100, 1, True, 3),

        scalar_row(1, 1, 1, "Noise", 100, 1, True, 4),

    ]

    check(rows, ["A", "B"], ["Energy > 0", "Energy > 0"], [], seed=92023)





def test_all_duplicates_pass():

    rows = [

        scalar_row(1, 1, 1, "A", 100, 1, True, 1),

        scalar_row(1, 1, 1, "A", 200, 1, True, 2),

        scalar_row(1, 1, 1, "B", 100, 1, True, 3),

        scalar_row(1, 1, 1, "B", 200, 1, True, 4),

        scalar_row(1, 1, 1, "Noise", -999, 999, False, 5),

    ]

    check(rows, ["A", "B"], ["Energy > 0", "Energy > 0"], rows, seed=92024)





def test_same_event_different_run():

    rows = [

        scalar_row(1, 1, 42, "A", 100, 1, True, 1),

        scalar_row(1, 1, 42, "B", 100, 1, True, 2),

        scalar_row(2, 1, 42, "A", -1, 1, True, 3),

        scalar_row(2, 1, 42, "B", 100, 1, True, 4),

    ]

    expected = [row for row in rows if row["RunNumber"] == 1]

    check(rows, ["A", "B"], ["Energy > 0", "Energy > 0"], expected, seed=92025)





def test_same_event_different_subrun():

    rows = [

        scalar_row(1, 10, 42, "A", 100, 1, True, 1),

        scalar_row(1, 10, 42, "B", 100, 1, True, 2),

        scalar_row(1, 11, 42, "A", -1, 1, True, 3),

        scalar_row(1, 11, 42, "B", 100, 1, True, 4),

    ]

    expected = [row for row in rows if row["SubrunNumber"] == 10]

    check(rows, ["A", "B"], ["Energy > 0", "Energy > 0"], expected, seed=92026)





def test_vector_one_false_element_rejects():

    rows = [

        {

            "RunNumber": 1, "SubrunNumber": 1, "IEventNb": 1,

            "Detector": "A", "EnergyVec": [100.0, 0.0, 100.0], "Payload": 1,

        },

        {

            "RunNumber": 1, "SubrunNumber": 1, "IEventNb": 1,

            "Detector": "B", "EnergyVec": [1.0, 2.0], "Payload": 2,

        },

    ]

    check(rows, ["A", "B"], ["EnergyVec > 10", "EnergyVec < 10"], [], seed=92027)





def test_empty_vector_cut_fails():

    rows = [

        {

            "RunNumber": 1, "SubrunNumber": 1, "IEventNb": 1,

            "Detector": "A", "EnergyVec": [], "Payload": 1,

        },

        {

            "RunNumber": 1, "SubrunNumber": 1, "IEventNb": 1,

            "Detector": "B", "EnergyVec": [], "Payload": 2,

        },

    ]

    check(rows, ["A", "B"], ["EnergyVec > 10", "EnergyVec < 10"], [], seed=92028)





def test_bool_vector_all_true():

    rows = [

        {

            "RunNumber": 1, "SubrunNumber": 1, "IEventNb": 1,

            "Detector": "A", "GoodVec": [True, True, True], "Payload": 1,

        },

        {

            "RunNumber": 1, "SubrunNumber": 1, "IEventNb": 1,

            "Detector": "B", "GoodVec": [True, True], "Payload": 2,

        },

    ]

    check(rows, ["A", "B"], ["GoodVec", "GoodVec"], rows, seed=92029)





def test_bool_vector_one_false():

    rows = [

        {

            "RunNumber": 1, "SubrunNumber": 1, "IEventNb": 1,

            "Detector": "A", "GoodVec": [True, False], "Payload": 1,

        },

        {

            "RunNumber": 1, "SubrunNumber": 1, "IEventNb": 1,

            "Detector": "B", "GoodVec": [True, True], "Payload": 2,

        },

    ]

    check(rows, ["A", "B"], ["GoodVec", "GoodVec"], [], seed=92030)





def test_detector_names_need_cpp_escaping():

    a = 'A"special'

    b = r"B****\p****ath"

    rows = [

        scalar_row(1, 1, 1, a, 100, 1, True, 1),

        scalar_row(1, 1, 1, b, 100, 1, True, 2),

    ]

    check(rows, [a, b], ["Energy > 0", "Energy > 0"], rows, seed=92031)





def test_many_unrelated_rows_preserved():

    """264 rows: two requested detectors plus 20 unrelated rows per event."""

    rows = []

    for event in range(12):  # 12 * 22 = 264 rows

        rows.extend([

            scalar_row(5, 6, event, "A", 100, 1, True, event * 100 + 1),

            scalar_row(5, 6, event, "B", 100, 1, True, event * 100 + 2),

        ])

        for extra in range(20):

            rows.append(

                scalar_row(

                    5, 6, event,

                    f"Noise{extra}",

                    -999,

                    999,

                    False,

                    event * 100 + 10 + extra,

                )

            )

    assert len(rows) == 264

    check(

        rows,

        ["A", "B"],

        ["Energy > 0", "Energy > 0"],

        rows,

        seed=92032,

    )



def test_detector_order_is_arbitrary():

    rows = [

        scalar_row(1, 1, 1, "A", 100, 1, True, 1),

        scalar_row(1, 1, 1, "B", 50, 1, True, 2),

        scalar_row(1, 1, 1, "C", 25, 1, True, 3),

    ]

    check(

        rows,

        ["C", "A", "B"],

        ["Energy > 20", "Energy > 90", "Energy > 40"],

        rows,

        seed=92033,

    )





def test_64_detectors_boundary_pass():

    detectors = [f"D{i}" for i in range(64)]

    rows = [

        scalar_row(1, 1, 1, detector, index + 1, 1, True, index)

        for index, detector in enumerate(detectors)

    ]

    check(

        rows,

        detectors,

        ["Energy > 0"] * 64,

        rows,

        seed=92034,

    )





def test_64_detectors_boundary_one_fails():

    detectors = [f"D{i}" for i in range(64)]

    rows = [

        scalar_row(

            1, 1, 1, detector,

            -1 if index == 63 else index + 1,

            1, True, index,

        )

        for index, detector in enumerate(detectors)

    ]

    check(

        rows,

        detectors,

        ["Energy > 0"] * 64,

        [],

        seed=92035,

    )





def _expect_failure(call, message):

    try:

        call()

    except Exception:

        return

    raise AssertionError(message)





def test_more_than_64_detectors_fails():

    detectors = [f"D{i}" for i in range(65)]

    dataframe = make_dataframe([

        scalar_row(1, 1, 1, "D0", 1, 1, True, 1)

    ])

    _expect_failure(

        lambda: detector_event_filter_cut_rdataframe(

            dataframe, detectors, ["Energy > 0"] * 65, "Detector", "IEventNb", "RunNumber", "SubrunNumber"

        ),

        "Expected >64 detectors to fail.",

    )





def test_duplicate_detector_names_fail():

    dataframe = make_dataframe([

        scalar_row(1, 1, 1, "A", 1, 1, True, 1)

    ])

    _expect_failure(

        lambda: detector_event_filter_cut_rdataframe(

            dataframe, ["A", "A"], ["Energy > 0", "Energy > 0"], "Detector", "IEventNb", "RunNumber", "SubrunNumber"

        ),

        "Expected duplicate detector names to fail.",

    )





def test_detector_cut_count_mismatch_fails():

    dataframe = make_dataframe([

        scalar_row(1, 1, 1, "A", 1, 1, True, 1)

    ])

    _expect_failure(

        lambda: detector_event_filter_cut_rdataframe(

            dataframe, ["A", "B"], ["Energy > 0"], "Detector", "IEventNb", "RunNumber", "SubrunNumber"

        ),

        "Expected detector/cut count mismatch.",

    )





def test_blank_detector_fails():

    dataframe = make_dataframe([

        scalar_row(1, 1, 1, "A", 1, 1, True, 1)

    ])

    _expect_failure(

        lambda: detector_event_filter_cut_rdataframe(

            dataframe, ["   "], ["Energy > 0"], "Detector", "IEventNb", "RunNumber", "SubrunNumber"

        ),

        "Expected blank detector to fail.",

    )





def test_blank_cut_fails():

    dataframe = make_dataframe([

        scalar_row(1, 1, 1, "A", 1, 1, True, 1)

    ])

    _expect_failure(

        lambda: detector_event_filter_cut_rdataframe(

            dataframe, ["A"], ["   "], "Detector"

        ),

        "Expected blank cut to fail.",

    )





def test_missing_event_key_column_fails():

    dataframe = make_dataframe([{

        "RunNumber": 1,

        "SubrunNumber": 1,

        "Detector": "A",

        "Energy": 1.0,

    }])

    _expect_failure(

        lambda: detector_event_filter_cut_rdataframe(

            dataframe, ["A"], ["Energy > 0"], "Detector", "IEventNb", "RunNumber", "SubrunNumber"

        ),

        "Expected missing IEventNb to fail.",

    )





def test_missing_detector_column_fails():

    dataframe = make_dataframe([{

        "RunNumber": 1,

        "SubrunNumber": 1,

        "IEventNb": 1,

        "WrongDetector": "A",

        "Energy": 1.0,

    }])

    _expect_failure(

        lambda: detector_event_filter_cut_rdataframe(

            dataframe, ["A"], ["Energy > 0"], "Detector", "IEventNb", "RunNumber", "SubrunNumber"

        ),

        "Expected missing detector column to fail.",

    )





def test_custom_key_columns():

    rows = [

        {"Run": 1, "Sub": 2, "Evt": 3, "Detector": "A", "Energy": 100.0, "Payload": 1},

        {"Run": 1, "Sub": 2, "Evt": 3, "Detector": "B", "Energy": 100.0, "Payload": 2},

    ]

    result = detector_event_filter_cut_rdataframe(

        make_dataframe(shuffled(rows, 92036)),

        ["A", "B"],

        ["Energy > 0", "Energy > 0"],

        "Detector",

        event_column="Evt",

        run_column="Run",

        subrun_column="Sub",

    )

    assert sorted(row["Payload"] for row in materialize(result, ["Payload"])) == [1, 2]





def test_big_final_1000_rows_complex():

    """Exactly 1000 rows covering multiple difficult grouping scenarios."""

    print(

        "\n"

        + "=" * 80

        + "\nBIG STRESS TEST: 1000 rows"

        + "\n  shuffled rows"

        + "\n  duplicate requested-detector rows"

        + "\n  missing requested detectors"

        + "\n  unrelated/noise detectors"

        + "\n  reused IEventNb across run/subrun keys"

        + "\n"

        + "=" * 80

    )

    rows = []

    # 100 groups * 10 rows = 1000 rows exactly.

    for group in range(100):

        run = 9000 + group % 4

        subrun = 9100 + (group // 4) % 5

        event = group % 13  # deliberately reused

        a_fail = group % 17 == 0

        b_fail = group % 19 == 0

        c_fail = group % 23 == 0

        c_missing = group % 29 == 0

        rows.extend([

            scalar_row(

                run, subrun, event,

                "A", 100, 5, True,

                group * 100 + 1,

            ),

            scalar_row(

                run, subrun, event,

                "A", -1 if a_fail else 120, 6, True,

                group * 100 + 2,

            ),

            scalar_row(

                run, subrun, event,

                "B", 100, 10, True,

                group * 100 + 3,

            ),

            scalar_row(

                run, subrun, event,

                "B", 100, 999 if b_fail else 11, True,

                group * 100 + 4,

            ),

        ])

        if c_missing:

            rows.append(

                scalar_row(

                    run, subrun, event,

                    "MissingCNoise", -500, 5000, False,

                    group * 100 + 5,

                )

            )

        else:

            rows.append(

                scalar_row(

                    run, subrun, event,

                    "C", 100, 12, not c_fail,

                    group * 100 + 5,

                )

            )

        for extra in range(5):

            rows.append(

                scalar_row(

                    run, subrun, event,

                    f"Noise{extra}",

                    -1000 - extra,

                    9000 + extra,

                    False,

                    group * 100 + 10 + extra,

                )

            )

    assert len(rows) == 1000

    detectors = ["A", "B", "C"]

    cuts = ["Energy > 0", "Time < 100", "Good"]

    expected = oracle(

        rows,

        detectors,

        lambda row, detector: (

            row["Energy"] > 0 if detector == "A"

            else row["Time"] < 100 if detector == "B"

            else row["Good"]

        ),

    )

    check(rows, detectors, cuts, expected, seed=99991)



def test_empty_vector_one_requested_detector_rejects_event():
    rows = [
        {
            "RunNumber": 10, "SubrunNumber": 1, "IEventNb": 7,
            "Detector": "A", "EnergyVec": [], "Payload": 1,
        },
        {
            "RunNumber": 10, "SubrunNumber": 1, "IEventNb": 7,
            "Detector": "B", "EnergyVec": [1.0, 2.0], "Payload": 2,
        },
        {
            "RunNumber": 10, "SubrunNumber": 1, "IEventNb": 7,
            "Detector": "Noise", "EnergyVec": [999.0], "Payload": 3,
        },
    ]

    check(
        rows,
        ["A", "B"],
        ["EnergyVec > 0", "EnergyVec < 10"],
        [],
        seed=93001,
    )


def test_empty_bool_vector_rejects_event():
    rows = [
        {
            "RunNumber": 11, "SubrunNumber": 2, "IEventNb": 8,
            "Detector": "A", "GoodVec": [], "Payload": 1,
        },
        {
            "RunNumber": 11, "SubrunNumber": 2, "IEventNb": 8,
            "Detector": "B", "GoodVec": [True, True], "Payload": 2,
        },
    ]

    check(
        rows,
        ["A", "B"],
        ["GoodVec", "GoodVec"],
        [],
        seed=93002,
    )


def test_empty_vector_duplicate_requested_row_rejects_event():
    rows = [
        {
            "RunNumber": 12, "SubrunNumber": 3, "IEventNb": 9,
            "Detector": "A", "EnergyVec": [10.0, 20.0], "Payload": 1,
        },
        {
            "RunNumber": 12, "SubrunNumber": 3, "IEventNb": 9,
            "Detector": "A", "EnergyVec": [], "Payload": 2,
        },
        {
            "RunNumber": 12, "SubrunNumber": 3, "IEventNb": 9,
            "Detector": "B", "EnergyVec": [1.0, 2.0], "Payload": 3,
        },
    ]

    check(
        rows,
        ["A", "B"],
        ["EnergyVec > 0", "EnergyVec < 10"],
        [],
        seed=93003,
    )


def test_empty_vector_unrelated_detector_does_not_reject():
    rows = [
        {
            "RunNumber": 13, "SubrunNumber": 4, "IEventNb": 10,
            "Detector": "A", "EnergyVec": [10.0, 20.0], "Payload": 1,
        },
        {
            "RunNumber": 13, "SubrunNumber": 4, "IEventNb": 10,
            "Detector": "B", "EnergyVec": [1.0, 2.0], "Payload": 2,
        },
        {
            "RunNumber": 13, "SubrunNumber": 4, "IEventNb": 10,
            "Detector": "Noise", "EnergyVec": [], "Payload": 3,
        },
    ]

    check(
        rows,
        ["A", "B"],
        ["EnergyVec > 0", "EnergyVec < 10"],
        rows,
        seed=93004,
    )


def test_empty_vector_nested_expression_rejects():
    rows = [
        {
            "RunNumber": 14, "SubrunNumber": 5, "IEventNb": 11,
            "Detector": "A",
            "EnergyVec": [],
            "GoodVec": [],
            "Threshold": 50.0,
            "Enabled": True,
            "Payload": 1,
        },
        {
            "RunNumber": 14, "SubrunNumber": 5, "IEventNb": 11,
            "Detector": "B",
            "EnergyVec": [10.0, 20.0],
            "GoodVec": [True, True],
            "Threshold": 100.0,
            "Enabled": True,
            "Payload": 2,
        },
    ]

    check(
        rows,
        ["A", "B"],
        [
            "Enabled && EnergyVec >= Threshold && GoodVec",
            "Enabled && EnergyVec < Threshold && GoodVec",
        ],
        [],
        seed=93005,
    )


def test_empty_vector_only_one_event_rejected_other_event_kept():
    rows = [
        {
            "RunNumber": 20, "SubrunNumber": 1, "IEventNb": 1,
            "Detector": "A", "EnergyVec": [], "Payload": 1,
        },
        {
            "RunNumber": 20, "SubrunNumber": 1, "IEventNb": 1,
            "Detector": "B", "EnergyVec": [1.0], "Payload": 2,
        },
        {
            "RunNumber": 20, "SubrunNumber": 1, "IEventNb": 2,
            "Detector": "A", "EnergyVec": [10.0, 20.0], "Payload": 3,
        },
        {
            "RunNumber": 20, "SubrunNumber": 1, "IEventNb": 2,
            "Detector": "B", "EnergyVec": [1.0, 2.0], "Payload": 4,
        },
    ]

    expected = [row for row in rows if row["IEventNb"] == 2]

    check(
        rows,
        ["A", "B"],
        ["EnergyVec > 0", "EnergyVec < 10"],
        expected,
        seed=93006,
    )


def test_empty_vector_same_event_number_different_run_isolated():
    rows = [
        {
            "RunNumber": 30, "SubrunNumber": 1, "IEventNb": 42,
            "Detector": "A", "EnergyVec": [], "Payload": 1,
        },
        {
            "RunNumber": 30, "SubrunNumber": 1, "IEventNb": 42,
            "Detector": "B", "EnergyVec": [1.0], "Payload": 2,
        },
        {
            "RunNumber": 31, "SubrunNumber": 1, "IEventNb": 42,
            "Detector": "A", "EnergyVec": [10.0], "Payload": 3,
        },
        {
            "RunNumber": 31, "SubrunNumber": 1, "IEventNb": 42,
            "Detector": "B", "EnergyVec": [1.0], "Payload": 4,
        },
    ]

    expected = [row for row in rows if row["RunNumber"] == 31]

    check(
        rows,
        ["A", "B"],
        ["EnergyVec > 0", "EnergyVec < 10"],
        expected,
        seed=93007,
    )


def test_empty_vector_same_event_number_different_subrun_isolated():
    rows = [
        {
            "RunNumber": 40, "SubrunNumber": 10, "IEventNb": 42,
            "Detector": "A", "EnergyVec": [], "Payload": 1,
        },
        {
            "RunNumber": 40, "SubrunNumber": 10, "IEventNb": 42,
            "Detector": "B", "EnergyVec": [1.0], "Payload": 2,
        },
        {
            "RunNumber": 40, "SubrunNumber": 11, "IEventNb": 42,
            "Detector": "A", "EnergyVec": [10.0], "Payload": 3,
        },
        {
            "RunNumber": 40, "SubrunNumber": 11, "IEventNb": 42,
            "Detector": "B", "EnergyVec": [1.0], "Payload": 4,
        },
    ]

    expected = [row for row in rows if row["SubrunNumber"] == 11]

    check(
        rows,
        ["A", "B"],
        ["EnergyVec > 0", "EnergyVec < 10"],
        expected,
        seed=93008,
    )


def test_empty_vector_three_requested_detectors_one_empty_rejects():
    rows = [
        {
            "RunNumber": 50, "SubrunNumber": 2, "IEventNb": 5,
            "Detector": "A", "EnergyVec": [10.0, 20.0], "Payload": 1,
        },
        {
            "RunNumber": 50, "SubrunNumber": 2, "IEventNb": 5,
            "Detector": "B", "EnergyVec": [], "Payload": 2,
        },
        {
            "RunNumber": 50, "SubrunNumber": 2, "IEventNb": 5,
            "Detector": "C", "EnergyVec": [5.0, 6.0], "Payload": 3,
        },
        {
            "RunNumber": 50, "SubrunNumber": 2, "IEventNb": 5,
            "Detector": "Noise", "EnergyVec": [999.0], "Payload": 4,
        },
    ]

    check(
        rows,
        ["A", "B", "C"],
        ["EnergyVec > 0", "EnergyVec < 100", "EnergyVec >= 5"],
        [],
        seed=93009,
    )


def test_empty_vector_mixed_with_nonempty_failing_duplicate():
    rows = [
        {
            "RunNumber": 60, "SubrunNumber": 3, "IEventNb": 6,
            "Detector": "A", "EnergyVec": [], "Payload": 1,
        },
        {
            "RunNumber": 60, "SubrunNumber": 3, "IEventNb": 6,
            "Detector": "A", "EnergyVec": [100.0, 0.0], "Payload": 2,
        },
        {
            "RunNumber": 60, "SubrunNumber": 3, "IEventNb": 6,
            "Detector": "B", "EnergyVec": [1.0, 2.0], "Payload": 3,
        },
        {
            "RunNumber": 60, "SubrunNumber": 3, "IEventNb": 6,
            "Detector": "Unrelated", "EnergyVec": [], "Payload": 4,
        },
    ]

    check(
        rows,
        ["A", "B"],
        ["EnergyVec > 0", "EnergyVec < 10"],
        [],
        seed=93010,
    )


EXPLICIT = [

    test_stress_shuffled_mixed_failures_240_rows,

    test_stress_reused_event_numbers_240_rows,

    test_stress_many_duplicates_270_rows,

    test_single_dataframe_returns_single,

    test_dataframe_list_returns_list,

    test_three_dataframes_independent,

    test_unrelated_failure_does_not_matter,

    test_missing_one_detector_rejects,

    test_all_requested_detectors_missing,

    test_one_bad_duplicate_rejects,

    test_same_event_different_run,

    test_same_event_different_subrun,

    test_vector_one_false_element_rejects,

    test_empty_vector_cut_fails,

    test_bool_vector_all_true,

    test_bool_vector_one_false,

    test_detector_names_need_cpp_escaping,

    test_many_unrelated_rows_preserved,

    test_detector_order_is_arbitrary,

    test_64_detectors_boundary_pass,

    test_64_detectors_boundary_one_fails,

    test_more_than_64_detectors_fails,

    test_duplicate_detector_names_fail,

    test_detector_cut_count_mismatch_fails,

    test_blank_detector_fails,

    test_blank_cut_fails,

    test_missing_event_key_column_fails,

    test_missing_detector_column_fails,

    test_custom_key_columns,

    test_big_final_1000_rows_complex,
    test_empty_vector_one_requested_detector_rejects_event,
    test_empty_bool_vector_rejects_event,
    test_empty_vector_duplicate_requested_row_rejects_event,
    test_empty_vector_unrelated_detector_does_not_reject,
    test_empty_vector_nested_expression_rejects,
    test_empty_vector_only_one_event_rejected_other_event_kept,
    test_empty_vector_same_event_number_different_run_isolated,
    test_empty_vector_same_event_number_different_subrun_isolated,
    test_empty_vector_three_requested_detectors_one_empty_rejects,
    test_empty_vector_mixed_with_nonempty_failing_duplicate,

]

assert len(EXPLICIT) == 40





# ===========================================================================

# Standalone runner

# ===========================================================================

def collect_tests():

    tests = list(GENERATED)

    tests.extend((test.__name__, test) for test in EXPLICIT)

    assert len(tests) == 160, (

        f"Suite must contain exactly 160 tests, got {len(tests)}."

    )

    names = [name for name, _ in tests]

    assert len(names) == len(set(names)), "Duplicate test names detected."

    return tests





def run_all_tests():

    tests = collect_tests()

    passed = 0

    failures = []

    suite_start = time.perf_counter()

    print(f"Running exactly {len(tests)} detector event-filter tests...\n")

    for index, (name, test) in enumerate(tests, start=1):

        started = time.perf_counter()

        try:

            test()

        except Exception as error:

            failures.append((name, error))

            print(

                f"[{index:03d}/{len(tests):03d}] FAIL {name} "

                f"({time.perf_counter() - started:.3f}s): "

                f"{type(error).__name__}: {error}"

            )

        else:

            passed += 1

            print(

                f"[{index:03d}/{len(tests):03d}] PASS {name} "

                f"({time.perf_counter() - started:.3f}s)"

            )

    print("\n" + "=" * 80)

    print(f"Passed: {passed}")

    print(f"Failed: {len(failures)}")

    print(f"Total:  {len(tests)}")

    print(f"Time:   {time.perf_counter() - suite_start:.3f}s")

    if failures:

        print("\nFailures:")

        for name, error in failures:

            print(f"\n{name}\n{type(error).__name__}: {error}")

        return 1

    print("\nAll 160 tests passed.")

    return 0





if __name__ == "__main__":

    raise SystemExit(run_all_tests())