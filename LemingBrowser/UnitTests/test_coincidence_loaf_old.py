"""
Exactly 150 standalone black-box stress tests for coincidence_loaf_old.

Target contract
---------------
For each (run, subrun, event) group:

* every detector requested in `detectors` must be present;
* if all are present, time_coinc is the arithmetic mean of time_column
  for the FIRST occurrence (in dataframe/input row order) of detectors[0]
  and the FIRST occurrence of detectors[1];
* exactly one row in the group receives that finite value: the first
  occurrence of detectors[0];
* all other rows receive NaN;
* if any requested detector is absent, every row in that group receives NaN.

The function under test is treated as a black box.  The oracle below is pure
Python and does not import or inspect implementation details.

Focus
-----
* deterministic random shuffling in every semantic test
* non-adjacent rows from the same (run, subrun, event)
* implicit-multithreaded ROOT.RDataFrame execution
* detector order matters: detectors[0] and detectors[1] define the average
* extra requested detectors gate coincidence but do not contribute to average
* duplicate detector rows, including duplicate first/second detector
* exactly one finite time_coinc per accepted event
* missing requested detectors => NaN everywhere in that group
* unrelated detector rows remain present and receive NaN
* reused event numbers across different run/subrun keys
* negative, fractional, large, inf and NaN time values
* std::string and RVec<Char_t> detector columns
* custom column names
* single RDF, lists/tuples of RDFs, repeated calls
* 64-detector boundary
* bounded stress dataframes, including one final 1000-row test
* API/error boundaries

Run:
    python test_coincidence_loaf_old_standalone.py
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
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

# Change only this import if your project stores the function elsewhere.
from Helpers.Coincidence.coincidence_loaf_old import coincidence_loaf_old


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


def _cpp_char_array(value: str) -> str:
    values = [str(byte) for byte in value.encode("utf-8")]
    values.append("0")
    return "ROOT::VecOps::RVec<Char_t>{" + ", ".join(values) + "}"


def _column_expression(values: list[Any]) -> str:
    first = values[0]

    if isinstance(first, CharArray):
        literals = [_cpp_char_array(value.value) for value in values]
        fallback = "ROOT::VecOps::RVec<Char_t>{0}"
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

    # Balanced tree keeps Cling nesting O(log N), including the 1000-row test.
    def build_tree(lo: int, hi: int) -> str:
        if lo >= hi:
            return fallback

        if hi - lo == 1:
            return (
                f"(rdfentry_ == {lo}ULL ? "
                f"{literals[lo]} : {fallback})"
            )

        mid = (lo + hi) // 2

        return (
            f"(rdfentry_ < {mid}ULL ? "
            f"{build_tree(lo, mid)} : "
            f"{build_tree(mid, hi)})"
        )

    return build_tree(0, len(literals))


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

def detector_text(value: Any) -> str:
    if isinstance(value, CharArray):
        return value.value
    return str(value)


def shuffled(rows: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    result = list(rows)
    random.Random(seed).shuffle(result)
    return result


def event_key(
    row: dict[str, Any],
    *,
    run_column: str,
    subrun_column: str,
    event_column: str,
) -> tuple[int, int, int]:
    return (
        int(row[run_column]),
        int(row[subrun_column]),
        int(row[event_column]),
    )


def oracle_time_coinc_by_payload(
    rows_in_actual_input_order: list[dict[str, Any]],
    detectors: list[str],
    *,
    detector_column: str,
    event_column: str,
    run_column: str,
    subrun_column: str,
    time_column: str,
    payload_column: str = "Payload",
) -> dict[int, float]:
    """
    Pure-Python black-box oracle.

    Every input payload starts with NaN.  For a group containing every
    requested detector, the first occurrence of detectors[0] receives:

        (first_time(detectors[0]) + first_time(detectors[1])) / 2

    No other row receives a finite value.
    """

    groups: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)

    for row in rows_in_actual_input_order:
        groups[
            event_key(
                row,
                run_column=run_column,
                subrun_column=subrun_column,
                event_column=event_column,
            )
        ].append(row)

    expected = {
        int(row[payload_column]): math.nan
        for row in rows_in_actual_input_order
    }

    for group in groups.values():
        first_by_detector: dict[str, dict[str, Any]] = {}

        for row in group:
            name = detector_text(row[detector_column])
            if name in detectors and name not in first_by_detector:
                first_by_detector[name] = row

        if not all(detector in first_by_detector for detector in detectors):
            continue

        row0 = first_by_detector[detectors[0]]
        row1 = first_by_detector[detectors[1]]

        t0 = float(row0[time_column])
        t1 = float(row1[time_column])

        expected[int(row0[payload_column])] = (t0 + t1) / 2.0

    return expected


def assert_float_same(actual: float, expected: float, *, context: str = "") -> None:
    actual = float(actual)
    expected = float(expected)

    if math.isnan(expected):
        assert math.isnan(actual), (
            f"{context}: expected NaN, got {actual!r}"
        )
        return

    if math.isinf(expected):
        assert actual == expected, (
            f"{context}: expected {expected!r}, got {actual!r}"
        )
        return

    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), (
        f"{context}: expected {expected!r}, got {actual!r}"
    )


def check(
    rows: list[dict[str, Any]],
    detectors: list[str],
    *,
    seed: int,
    detector_column: str = "Detector",
    event_column: str = "IEventNb",
    run_column: str = "RunNumber",
    subrun_column: str = "SubrunNumber",
    time_column: str = "Itime",
    payload_column: str = "Payload",
) -> None:
    input_rows = shuffled(rows, seed)

    expected = oracle_time_coinc_by_payload(
        input_rows,
        detectors,
        detector_column=detector_column,
        event_column=event_column,
        run_column=run_column,
        subrun_column=subrun_column,
        time_column=time_column,
        payload_column=payload_column,
    )

    t0 = time.perf_counter()
    dataframe = make_dataframe(input_rows)
    t1 = time.perf_counter()

    result = coincidence_loaf_old(
        dataframe,
        detectors,
        detector_column,
        event_column,
        run_column,
        subrun_column,
        time_column,
    )
    t2 = time.perf_counter()

    actual_rows = materialize(
        result,
        [payload_column, "time_coinc"],
    )
    t3 = time.perf_counter()

    assert len(actual_rows) == len(input_rows), (
        "coincidence_loaf_old must annotate, not filter rows: "
        f"input={len(input_rows)}, output={len(actual_rows)}"
    )

    actual_by_payload = {
        int(row[payload_column]): float(row["time_coinc"])
        for row in actual_rows
    }

    assert set(actual_by_payload) == set(expected)

    for payload, expected_value in expected.items():
        assert_float_same(
            actual_by_payload[payload],
            expected_value,
            context=f"payload={payload}, detectors={detectors}",
        )

    # Independent invariant: at most one finite/non-NaN cell per group.
    # Inf is considered a written coincidence value too.
    source_by_payload = {
        int(row[payload_column]): row
        for row in input_rows
    }

    written_per_group: dict[tuple[int, int, int], int] = defaultdict(int)

    for payload, value in actual_by_payload.items():
        if not math.isnan(value):
            row = source_by_payload[payload]
            written_per_group[
                event_key(
                    row,
                    run_column=run_column,
                    subrun_column=subrun_column,
                    event_column=event_column,
                )
            ] += 1

    assert all(count <= 1 for count in written_per_group.values()), (
        f"More than one time_coinc entry found in an event group: "
        f"{written_per_group}"
    )

    print(
        f"build={t1 - t0:.3f}s | "
        f"call/setup={t2 - t1:.3f}s | "
        f"materialize={t3 - t2:.3f}s"
    )


# ===========================================================================
# Common row factory
# ===========================================================================

def row(
    run: int,
    subrun: int,
    event: int,
    detector: Any,
    itime: float,
    payload: int,
    *,
    energy: float = 0.0,
    good: bool = True,
) -> dict[str, Any]:
    return {
        "RunNumber": int(run),
        "SubrunNumber": int(subrun),
        "IEventNb": int(event),
        "Detector": detector,
        "Itime": float(itime),
        "Energy": float(energy),
        "Good": bool(good),
        "Payload": int(payload),
    }


# ===========================================================================
# Generated tests: exactly 120
# ===========================================================================

GENERATED: list[tuple[str, Any]] = []


def add_generated(name: str, fn) -> None:
    GENERATED.append((f"test_{name}", fn))


# ---------------------------------------------------------------------------
# 1-30: random 2-detector groups, duplicates, noise, missing rows.
# ---------------------------------------------------------------------------

for case in range(30):
    def test(case=case):
        rng = random.Random(10000 + case)
        rows = []

        for g in range(35 + case):
            run = 1 + g // 18
            subrun = 10 + (g // 9) % 2
            event = g % 9

            for detector_index, detector in enumerate(("A", "B")):
                copies = 1 + rng.randrange(3)

                if (g + detector_index + case) % 17 == 0:
                    copies = 0

                for copy_index in range(copies):
                    rows.append(
                        row(
                            run,
                            subrun,
                            event,
                            detector,
                            rng.uniform(-1000.0, 1000.0),
                            case * 1_000_000
                            + g * 100
                            + detector_index * 10
                            + copy_index,
                            energy=rng.uniform(-50, 500),
                            good=rng.random() > 0.1,
                        )
                    )

            for noise in range(rng.randrange(5)):
                rows.append(
                    row(
                        run,
                        subrun,
                        event,
                        f"Noise{noise}",
                        9000.0 + noise,
                        case * 1_000_000 + g * 100 + 80 + noise,
                        energy=-999,
                        good=False,
                    )
                )

        check(
            rows,
            ["A", "B"],
            seed=20000 + case,
        )

    add_generated(f"random_two_detector_groups_{case:02d}", test)


# ---------------------------------------------------------------------------
# 31-50: 3-6 requested detectors. Only first two contribute to time.
# Extra requested detectors only gate acceptance.
# ---------------------------------------------------------------------------

for case in range(20):
    def test(case=case):
        rng = random.Random(30000 + case)
        detector_count = 3 + case % 4
        detectors = [f"D{i}" for i in range(detector_count)]
        rows = []

        for g in range(45):
            run = 100 + g // 15
            subrun = 200 + (g // 5) % 3
            event = g % 5

            for detector_index, detector in enumerate(detectors):
                if (
                    detector_index >= 2
                    and (g + case + detector_index) % 19 == 0
                ):
                    continue

                copies = 1 + (
                    1
                    if detector_index < 2 and (g + case) % 4 == 0
                    else 0
                )

                for copy_index in range(copies):
                    rows.append(
                        row(
                            run,
                            subrun,
                            event,
                            detector,
                            1000.0 * detector_index
                            + g
                            + copy_index * 0.125
                            + rng.random() * 0.01,
                            case * 1_000_000
                            + g * 100
                            + detector_index * 10
                            + copy_index,
                        )
                    )

            rows.append(
                row(
                    run,
                    subrun,
                    event,
                    "Irrelevant",
                    -123456.0,
                    case * 1_000_000 + g * 100 + 99,
                    good=False,
                )
            )

        check(
            rows,
            detectors,
            seed=40000 + case,
        )

    add_generated(f"extra_requested_gate_only_{case:02d}", test)


# ---------------------------------------------------------------------------
# 51-70: detector ordering. Same rows, many permutations/order choices.
# ---------------------------------------------------------------------------

for case in range(20):
    def test(case=case):
        rng = random.Random(50000 + case)
        base = ["Alpha", "Beta", "Gamma", "Delta"]
        rng.shuffle(base)

        detectors = base[: 2 + case % 3]
        rows = []

        for g in range(50):
            run = 300 + g // 20
            subrun = 400 + (g // 10) % 2
            event = g % 10

            # Give every detector very different time scales so using the
            # wrong detector pair is immediately visible.
            for detector_index, detector in enumerate(base):
                rows.append(
                    row(
                        run,
                        subrun,
                        event,
                        detector,
                        (detector_index + 1) * 10000.0 + g * 1.25,
                        case * 1_000_000 + g * 100 + detector_index,
                    )
                )

                if detector in detectors[:2] and (g + case) % 5 == 0:
                    rows.append(
                        row(
                            run,
                            subrun,
                            event,
                            detector,
                            -(detector_index + 1) * 50000.0 - g,
                            case * 1_000_000 + g * 100 + 50 + detector_index,
                        )
                    )

            # Occasionally remove a gating detector beyond first two.
            if len(detectors) > 2 and (g + case) % 13 == 0:
                victim = detectors[-1]
                rows = [
                    r
                    for r in rows
                    if not (
                        r["RunNumber"] == run
                        and r["SubrunNumber"] == subrun
                        and r["IEventNb"] == event
                        and r["Detector"] == victim
                    )
                ]

        check(
            rows,
            detectors,
            seed=60000 + case,
        )

    add_generated(f"detector_order_controls_average_{case:02d}", test)


# ---------------------------------------------------------------------------
# 71-85: full triple key; intentionally reuse event numbers aggressively.
# ---------------------------------------------------------------------------

for case in range(15):
    def test(case=case):
        rows = []

        payload = case * 10_000_000

        for run_offset in range(5):
            for subrun_offset in range(4):
                for event in range(6):
                    run_number = 1000 + run_offset
                    subrun_number = 2000 + subrun_offset

                    rows.append(
                        row(
                            run_number,
                            subrun_number,
                            event,
                            "A",
                            run_offset * 1000
                            + subrun_offset * 100
                            + event
                            + 0.1,
                            payload + 1,
                        )
                    )
                    payload += 1

                    # Some specific triple keys miss B.
                    if (
                        run_offset * 100
                        + subrun_offset * 10
                        + event
                        + case
                    ) % 11 != 0:
                        rows.append(
                            row(
                                run_number,
                                subrun_number,
                                event,
                                "B",
                                -run_offset * 2000
                                - subrun_offset * 200
                                - event
                                - 0.2,
                                payload + 1,
                            )
                        )
                        payload += 1

                    rows.append(
                        row(
                            run_number,
                            subrun_number,
                            event,
                            "Noise",
                            999999.0,
                            payload + 1,
                            good=False,
                        )
                    )
                    payload += 1

        check(
            rows,
            ["A", "B"],
            seed=70000 + case,
        )

    add_generated(f"full_run_subrun_event_key_{case:02d}", test)


# ---------------------------------------------------------------------------
# 86-100: RVec<Char_t> detector names.
# ---------------------------------------------------------------------------

for case in range(15):
    def test(case=case):
        rows = []

        for g in range(45):
            run_number = 3000 + g // 15
            subrun_number = 4000 + (g // 5) % 3
            event = g % 5

            names = ["A", "B", "Gate"]

            if (g + case) % 13 == 0:
                names.remove("Gate")

            for detector_index, detector in enumerate(names):
                rows.append(
                    row(
                        run_number,
                        subrun_number,
                        event,
                        CharArray(detector),
                        detector_index * 100.0 + g + case / 100.0,
                        case * 1_000_000 + g * 10 + detector_index,
                    )
                )

            rows.append(
                row(
                    run_number,
                    subrun_number,
                    event,
                    CharArray("Other"),
                    -99999.0,
                    case * 1_000_000 + g * 10 + 9,
                )
            )

        check(
            rows,
            ["A", "B", "Gate"],
            detector_column="Detector",
            seed=80000 + case,
        )

    add_generated(f"char_array_detector_names_{case:02d}", test)


# ---------------------------------------------------------------------------
# 101-110: special numeric times.
# ---------------------------------------------------------------------------

for case in range(10):
    def test(case=case):
        rows = []

        values = [
            (-10.5, 20.25),
            (0.0, 0.0),
            (1e-12, 2e-12),
            (1e12, -1e12),
            (-999999.125, -0.875),
            (math.inf, 5.0),
            (-math.inf, -5.0),
            (math.nan, 10.0),
            (10.0, math.nan),
            (123.4567890123, -987.6543210987),
        ]

        for g in range(30):
            a_time, b_time = values[(g + case) % len(values)]

            rows.extend([
                row(
                    5000 + g // 10,
                    6000 + (g // 5) % 2,
                    g % 5,
                    "A",
                    a_time,
                    case * 1_000_000 + g * 10 + 1,
                ),
                row(
                    5000 + g // 10,
                    6000 + (g // 5) % 2,
                    g % 5,
                    "B",
                    b_time,
                    case * 1_000_000 + g * 10 + 2,
                ),
                row(
                    5000 + g // 10,
                    6000 + (g // 5) % 2,
                    g % 5,
                    "Other",
                    777777.0,
                    case * 1_000_000 + g * 10 + 3,
                ),
            ])

        check(
            rows,
            ["A", "B"],
            seed=90000 + case,
        )

    add_generated(f"special_numeric_times_{case:02d}", test)


# ---------------------------------------------------------------------------
# 111-120: dense duplicate first/second-detector cases.
# ---------------------------------------------------------------------------

for case in range(10):
    def test(case=case):
        rng = random.Random(100000 + case)
        rows = []

        for g in range(25):
            run_number = 7000 + g // 10
            subrun_number = 8000 + (g // 5) % 2
            event = g % 5

            for copy_index in range(6):
                rows.append(
                    row(
                        run_number,
                        subrun_number,
                        event,
                        "A",
                        100.0 + g * 10 + copy_index,
                        case * 1_000_000 + g * 100 + copy_index,
                    )
                )

            for copy_index in range(5):
                rows.append(
                    row(
                        run_number,
                        subrun_number,
                        event,
                        "B",
                        -200.0 - g * 10 - copy_index,
                        case * 1_000_000 + g * 100 + 20 + copy_index,
                    )
                )

            # Gating detector sometimes missing.
            if (g + case) % 9 != 0:
                rows.append(
                    row(
                        run_number,
                        subrun_number,
                        event,
                        "C",
                        rng.uniform(-5000, 5000),
                        case * 1_000_000 + g * 100 + 40,
                    )
                )

            for noise in range(4):
                rows.append(
                    row(
                        run_number,
                        subrun_number,
                        event,
                        f"Noise{noise}",
                        rng.uniform(-1e6, 1e6),
                        case * 1_000_000 + g * 100 + 50 + noise,
                    )
                )

        check(
            rows,
            ["A", "B", "C"],
            seed=110000 + case,
        )

    add_generated(f"dense_duplicate_first_second_{case:02d}", test)


assert len(GENERATED) == 120


# ===========================================================================
# Explicit tests: exactly 30
# ===========================================================================

def _expect_failure(call, message: str) -> None:
    try:
        call()
    except Exception:
        return
    raise AssertionError(message)


def basic_dataframe():
    return make_dataframe([
        row(1, 1, 1, "A", 10.0, 1),
        row(1, 1, 1, "B", 20.0, 2),
    ])


def test_single_dataframe_returns_single():
    result = coincidence_loaf_old(
        basic_dataframe(),
        ["A", "B"],
        "Detector",
        "IEventNb",
        "RunNumber",
        "SubrunNumber",
        "Itime",
    )

    assert not isinstance(result, (list, tuple))
    rows = materialize(result, ["Payload", "time_coinc"])
    assert len(rows) == 2


def test_dataframe_list_returns_list():
    dfs = [
        make_dataframe(shuffled([
            row(1, 1, 1, "A", 10, 1),
            row(1, 1, 1, "B", 20, 2),
        ], 120001)),
        make_dataframe(shuffled([
            row(2, 2, 2, "A", 30, 3),
            row(2, 2, 2, "B", 50, 4),
        ], 120002)),
    ]

    results = coincidence_loaf_old(
        dfs,
        ["A", "B"],
        "Detector",
        "IEventNb",
        "RunNumber",
        "SubrunNumber",
        "Itime",
    )

    assert isinstance(results, list)
    assert len(results) == 2

    for result in results:
        assert len(materialize(result, ["Payload", "time_coinc"])) == 2


def test_dataframe_tuple_returns_list():
    dfs = (
        make_dataframe(shuffled([
            row(1, 1, 1, "A", 1, 1),
            row(1, 1, 1, "B", 3, 2),
        ], 120003)),
        make_dataframe(shuffled([
            row(2, 2, 2, "A", 2, 3),
            row(2, 2, 2, "B", 6, 4),
        ], 120004)),
    )

    results = coincidence_loaf_old(
        dfs,
        ["A", "B"],
        "Detector",
        "IEventNb",
        "RunNumber",
        "SubrunNumber",
        "Itime",
    )

    assert isinstance(results, list)
    assert len(results) == 2


def test_three_dataframes_independent():
    datasets = []

    for dataset in range(3):
        rows = []

        for event in range(40):
            rows.append(row(dataset, 1, event, "A", dataset * 1000 + event, event * 10 + 1))
            if event % (7 + dataset) != 0:
                rows.append(row(dataset, 1, event, "B", -dataset * 1000 - event, event * 10 + 2))

        datasets.append(make_dataframe(shuffled(rows, 121000 + dataset)))

    results = coincidence_loaf_old(
        datasets,
        ["A", "B"],
        "Detector",
        "IEventNb",
        "RunNumber",
        "SubrunNumber",
        "Itime",
    )

    assert len(results) == 3

    for dataset, result in enumerate(results):
        actual = materialize(result, ["time_coinc"])
        expected_written = sum(
            1
            for event in range(40)
            if event % (7 + dataset) != 0
        )
        assert sum(not math.isnan(float(r["time_coinc"])) for r in actual) == expected_written


def test_missing_second_detector_nan_everywhere():
    rows = [
        row(1, 1, 1, "A", 10, 1),
        row(1, 1, 1, "Noise", 20, 2),
    ]
    check(rows, ["A", "B"], seed=122001)


def test_missing_first_detector_nan_everywhere():
    rows = [
        row(1, 1, 1, "B", 10, 1),
        row(1, 1, 1, "Noise", 20, 2),
    ]
    check(rows, ["A", "B"], seed=122002)


def test_missing_third_gating_detector_nan_everywhere():
    rows = [
        row(1, 1, 1, "A", 10, 1),
        row(1, 1, 1, "B", 20, 2),
        row(1, 1, 1, "Noise", 30, 3),
    ]
    check(rows, ["A", "B", "C"], seed=122003)


def test_unrelated_rows_preserved_and_nan():
    rows = [
        row(1, 1, 1, "A", 10, 1),
        row(1, 1, 1, "B", 20, 2),
    ]

    for index in range(30):
        rows.append(
            row(
                1,
                1,
                1,
                f"Noise{index}",
                1e6 + index,
                100 + index,
            )
        )

    check(rows, ["A", "B"], seed=122004)


def test_same_event_different_run_independent():
    rows = [
        row(1, 10, 42, "A", 10, 1),
        row(1, 10, 42, "B", 20, 2),
        row(2, 10, 42, "A", 100, 3),
        # run 2 deliberately missing B
    ]
    check(rows, ["A", "B"], seed=122005)


def test_same_event_different_subrun_independent():
    rows = [
        row(1, 10, 42, "A", 10, 1),
        row(1, 10, 42, "B", 20, 2),
        row(1, 11, 42, "A", 100, 3),
        # subrun 11 deliberately missing B
    ]
    check(rows, ["A", "B"], seed=122006)


def test_detector_order_reversal_changes_target_and_value_pair_order_not_mean():
    rows = [
        row(1, 1, 1, "A", 10, 1),
        row(1, 1, 1, "B", 30, 2),
        row(1, 1, 1, "C", 1000, 3),
    ]

    # Reversal leaves arithmetic mean numerically equal, but the written row
    # must switch from first A to first B.
    check(rows, ["B", "A", "C"], seed=122007)


def test_first_two_only_third_time_irrelevant():
    rows = [
        row(1, 1, 1, "A", 10, 1),
        row(1, 1, 1, "B", 20, 2),
        row(1, 1, 1, "C", 9.9e99, 3),
    ]
    check(rows, ["A", "B", "C"], seed=122008)


def test_custom_column_names():
    rows = [
        {
            "Run": 7,
            "Sub": 8,
            "Evt": 9,
            "Det": "A",
            "Clock": 12.5,
            "Payload": 1,
        },
        {
            "Run": 7,
            "Sub": 8,
            "Evt": 9,
            "Det": "B",
            "Clock": 17.5,
            "Payload": 2,
        },
        {
            "Run": 7,
            "Sub": 8,
            "Evt": 9,
            "Det": "Other",
            "Clock": 999.0,
            "Payload": 3,
        },
    ]

    check(
        rows,
        ["A", "B"],
        seed=122009,
        detector_column="Det",
        event_column="Evt",
        run_column="Run",
        subrun_column="Sub",
        time_column="Clock",
    )


def test_special_detector_names_cpp_escaping():
    a = 'A"special'
    b = r"B\path"
    rows = [
        row(1, 1, 1, a, 11.0, 1),
        row(1, 1, 1, b, 13.0, 2),
    ]
    check(rows, [a, b], seed=122010)


def test_64_detectors_boundary_pass():
    detectors = [f"D{i}" for i in range(64)]
    rows = [
        row(1, 1, 1, detector, index * 10.0, index)
        for index, detector in enumerate(detectors)
    ]
    check(rows, detectors, seed=122011)


def test_64_detectors_one_missing_nan_everywhere():
    detectors = [f"D{i}" for i in range(64)]
    rows = [
        row(1, 1, 1, detector, index * 10.0, index)
        for index, detector in enumerate(detectors[:-1])
    ]
    check(rows, detectors, seed=122012)


def test_more_than_64_detectors_fails():
    detectors = [f"D{i}" for i in range(65)]

    _expect_failure(
        lambda: coincidence_loaf_old(
            basic_dataframe(),
            detectors,
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected >64 detectors to fail.",
    )


def test_one_detector_fails():
    _expect_failure(
        lambda: coincidence_loaf_old(
            basic_dataframe(),
            ["A"],
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected fewer than two detectors to fail.",
    )


def test_zero_detectors_fails():
    _expect_failure(
        lambda: coincidence_loaf_old(
            basic_dataframe(),
            [],
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected zero detectors to fail.",
    )


def test_string_instead_of_detector_list_fails():
    _expect_failure(
        lambda: coincidence_loaf_old(
            basic_dataframe(),
            "AB",
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected detectors=str to fail.",
    )


def test_duplicate_detector_names_fail():
    _expect_failure(
        lambda: coincidence_loaf_old(
            basic_dataframe(),
            ["A", "A"],
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected duplicate detector names to fail.",
    )


def test_blank_detector_name_fails():
    _expect_failure(
        lambda: coincidence_loaf_old(
            basic_dataframe(),
            ["A", "   "],
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected blank detector name to fail.",
    )


def test_non_string_detector_name_fails():
    _expect_failure(
        lambda: coincidence_loaf_old(
            basic_dataframe(),
            ["A", 123],
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected non-string detector name to fail.",
    )


def test_missing_detector_column_fails():
    dataframe = make_dataframe([
        {
            "RunNumber": 1,
            "SubrunNumber": 1,
            "IEventNb": 1,
            "WrongDetector": "A",
            "Itime": 1.0,
            "Payload": 1,
        }
    ])

    _expect_failure(
        lambda: coincidence_loaf_old(
            dataframe,
            ["A", "B"],
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected missing detector column to fail.",
    )


def test_missing_event_column_fails():
    dataframe = make_dataframe([
        {
            "RunNumber": 1,
            "SubrunNumber": 1,
            "Detector": "A",
            "Itime": 1.0,
            "Payload": 1,
        }
    ])

    _expect_failure(
        lambda: coincidence_loaf_old(
            dataframe,
            ["A", "B"],
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected missing event column to fail.",
    )


def test_missing_run_column_fails():
    dataframe = make_dataframe([
        {
            "SubrunNumber": 1,
            "IEventNb": 1,
            "Detector": "A",
            "Itime": 1.0,
            "Payload": 1,
        }
    ])

    _expect_failure(
        lambda: coincidence_loaf_old(
            dataframe,
            ["A", "B"],
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected missing run column to fail.",
    )


def test_missing_subrun_column_fails():
    dataframe = make_dataframe([
        {
            "RunNumber": 1,
            "IEventNb": 1,
            "Detector": "A",
            "Itime": 1.0,
            "Payload": 1,
        }
    ])

    _expect_failure(
        lambda: coincidence_loaf_old(
            dataframe,
            ["A", "B"],
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected missing subrun column to fail.",
    )


def test_missing_time_column_fails():
    dataframe = make_dataframe([
        {
            "RunNumber": 1,
            "SubrunNumber": 1,
            "IEventNb": 1,
            "Detector": "A",
            "WrongTime": 1.0,
            "Payload": 1,
        }
    ])

    _expect_failure(
        lambda: coincidence_loaf_old(
            dataframe,
            ["A", "B"],
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected missing time column to fail.",
    )


def test_existing_time_coinc_column_fails():
    dataframe = make_dataframe([
        {
            "RunNumber": 1,
            "SubrunNumber": 1,
            "IEventNb": 1,
            "Detector": "A",
            "Itime": 1.0,
            "time_coinc": 999.0,
            "Payload": 1,
        },
        {
            "RunNumber": 1,
            "SubrunNumber": 1,
            "IEventNb": 1,
            "Detector": "B",
            "Itime": 2.0,
            "time_coinc": 999.0,
            "Payload": 2,
        },
    ])

    _expect_failure(
        lambda: coincidence_loaf_old(
            dataframe,
            ["A", "B"],
            "Detector",
            "IEventNb",
            "RunNumber",
            "SubrunNumber",
            "Itime",
        ),
        "Expected pre-existing time_coinc column to fail.",
    )


def test_repeated_calls_independent():
    rows1 = shuffled([
        row(1, 1, 1, "A", 10, 1),
        row(1, 1, 1, "B", 20, 2),
    ], 123001)

    rows2 = shuffled([
        row(2, 2, 2, "X", -100, 11),
        row(2, 2, 2, "Y", 300, 12),
        row(2, 2, 2, "Z", 999999, 13),
    ], 123002)

    result1 = coincidence_loaf_old(
        make_dataframe(rows1),
        ["A", "B"],
        "Detector",
        "IEventNb",
        "RunNumber",
        "SubrunNumber",
        "Itime",
    )

    result2 = coincidence_loaf_old(
        make_dataframe(rows2),
        ["X", "Y", "Z"],
        "Detector",
        "IEventNb",
        "RunNumber",
        "SubrunNumber",
        "Itime",
    )

    actual1 = {
        int(r["Payload"]): float(r["time_coinc"])
        for r in materialize(result1, ["Payload", "time_coinc"])
    }
    actual2 = {
        int(r["Payload"]): float(r["time_coinc"])
        for r in materialize(result2, ["Payload", "time_coinc"])
    }

    expected1 = oracle_time_coinc_by_payload(
        rows1,
        ["A", "B"],
        detector_column="Detector",
        event_column="IEventNb",
        run_column="RunNumber",
        subrun_column="SubrunNumber",
        time_column="Itime",
    )
    expected2 = oracle_time_coinc_by_payload(
        rows2,
        ["X", "Y", "Z"],
        detector_column="Detector",
        event_column="IEventNb",
        run_column="RunNumber",
        subrun_column="SubrunNumber",
        time_column="Itime",
    )

    for payload, value in expected1.items():
        assert_float_same(actual1[payload], value)
    for payload, value in expected2.items():
        assert_float_same(actual2[payload], value)


def test_big_final_1000_rows_complex():
    """
    Exactly 1000 rows:
      * 100 independently keyed groups
      * duplicate first and second detectors
      * optional missing gating detector
      * five unrelated rows per group
      * reused event numbers
      * complete deterministic shuffle
    """

    print(
        "\n"
        + "=" * 80
        + "\nBIG COINCIDENCE STRESS TEST: exactly 1000 rows"
        + "\n  shuffled rows"
        + "\n  duplicate first/second detectors"
        + "\n  missing third gating detector"
        + "\n  unrelated/noise detectors"
        + "\n  reused event numbers across run/subrun"
        + "\n"
        + "=" * 80
    )

    rows = []

    # 100 groups * 10 rows = exactly 1000.
    for group in range(100):
        run_number = 9000 + group % 4
        subrun_number = 9100 + (group // 4) % 5
        event = group % 13

        rows.extend([
            row(
                run_number, subrun_number, event,
                "A", 1000 + group * 10 + 1,
                group * 100 + 1,
            ),
            row(
                run_number, subrun_number, event,
                "A", -1000 - group * 10 - 2,
                group * 100 + 2,
            ),
            row(
                run_number, subrun_number, event,
                "B", 2000 + group * 10 + 3,
                group * 100 + 3,
            ),
            row(
                run_number, subrun_number, event,
                "B", -2000 - group * 10 - 4,
                group * 100 + 4,
            ),
        ])

        if group % 17 == 0:
            rows.append(
                row(
                    run_number, subrun_number, event,
                    "MissingCNoise", 5e8,
                    group * 100 + 5,
                )
            )
        else:
            rows.append(
                row(
                    run_number, subrun_number, event,
                    "C", 9e8 + group,
                    group * 100 + 5,
                )
            )

        for extra in range(5):
            rows.append(
                row(
                    run_number, subrun_number, event,
                    f"Noise{extra}",
                    1e12 + group * 100 + extra,
                    group * 100 + 10 + extra,
                    good=False,
                )
            )

    assert len(rows) == 1000

    check(
        rows,
        ["A", "B", "C"],
        seed=99991,
    )


EXPLICIT = [
    test_single_dataframe_returns_single,
    test_dataframe_list_returns_list,
    test_dataframe_tuple_returns_list,
    test_three_dataframes_independent,
    test_missing_second_detector_nan_everywhere,
    test_missing_first_detector_nan_everywhere,
    test_missing_third_gating_detector_nan_everywhere,
    test_unrelated_rows_preserved_and_nan,
    test_same_event_different_run_independent,
    test_same_event_different_subrun_independent,
    test_detector_order_reversal_changes_target_and_value_pair_order_not_mean,
    test_first_two_only_third_time_irrelevant,
    test_custom_column_names,
    test_special_detector_names_cpp_escaping,
    test_64_detectors_boundary_pass,
    test_64_detectors_one_missing_nan_everywhere,
    test_more_than_64_detectors_fails,
    test_one_detector_fails,
    test_zero_detectors_fails,
    test_string_instead_of_detector_list_fails,
    test_duplicate_detector_names_fail,
    test_blank_detector_name_fails,
    test_non_string_detector_name_fails,
    test_missing_detector_column_fails,
    test_missing_event_column_fails,
    test_missing_run_column_fails,
    test_missing_subrun_column_fails,
    test_missing_time_column_fails,
    test_existing_time_coinc_column_fails,
    test_repeated_calls_independent,
    test_big_final_1000_rows_complex,
]

# We want exactly 30 explicit tests.  The big stress test is included by
# replacing one redundant explicit slot below rather than creating 31.
# Keep the strongest 30.
EXPLICIT.remove(test_first_two_only_third_time_irrelevant)

assert len(EXPLICIT) == 30


# ===========================================================================
# Standalone runner
# ===========================================================================

def collect_tests():
    tests = list(GENERATED)
    tests.extend((test.__name__, test) for test in EXPLICIT)

    assert len(tests) == 150, (
        f"Suite must contain exactly 150 tests, got {len(tests)}."
    )

    names = [name for name, _ in tests]
    assert len(names) == len(set(names)), "Duplicate test names detected."

    return tests


def run_all_tests():
    tests = collect_tests()

    passed = 0
    failures = []
    suite_start = time.perf_counter()

    print(
        f"Running exactly {len(tests)} coincidence_loaf_old "
        f"black-box tests...\n"
    )

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
            print(
                f"\n{name}\n"
                f"{type(error).__name__}: {error}"
            )

        return 1

    print("\nAll 150 coincidence_loaf_old tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_all_tests())