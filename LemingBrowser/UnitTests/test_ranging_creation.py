import math
import ROOT
from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from Helpers.Ranging.create_ranging_points import calculate_entries_per_muon_hit,rangingError


# ============================================================
# Helper
# ============================================================

def create_muon_dataframe(number_of_entries, hit_entries):
    """
    Create an RDataFrame where hasMuonHit == 1
    for the specified rdfentry_ values.
    """

    if not hit_entries:
        expression = "false"
    else:
        expression = " || ".join(
            f"rdfentry_ == {entry}"
            for entry in hit_entries
        )

    return (
        ROOT.RDataFrame(number_of_entries)
        .Define(
            "hasMuonHit",
            expression,
        )
    )


# ============================================================
# Test 1
# ============================================================

def test_single_dataframe():
    muon_number_dataframe = create_muon_dataframe(
        number_of_entries=5,
        hit_entries=[0, 2],
    )

    muon_dataframe = ROOT.RDataFrame(10)

    result = calculate_entries_per_muon_hit(
        muon_dataframes=[muon_dataframe],
        muon_number_dataframes=[muon_number_dataframe],
        energies=[10.0],
    )

    # 10 entries / 2 hits = 5
    assert result == [
        (10.0, 5.0),
    ]


# ============================================================
# Test 2
# ============================================================

def test_multiple_dataframes():
    muon_number_dataframe_1 = create_muon_dataframe(
        number_of_entries=5,
        hit_entries=[0, 1],
    )

    muon_number_dataframe_2 = create_muon_dataframe(
        number_of_entries=6,
        hit_entries=[0, 1, 2],
    )

    muon_dataframe_1 = ROOT.RDataFrame(10)
    muon_dataframe_2 = ROOT.RDataFrame(12)

    result = calculate_entries_per_muon_hit(
        muon_dataframes=[
            muon_dataframe_1,
            muon_dataframe_2,
        ],
        muon_number_dataframes=[
            muon_number_dataframe_1,
            muon_number_dataframe_2,
        ],
        energies=[
            10.0,
            20.0,
        ],
    )

    assert result == [
        (10.0, 5.0),  # 10 / 2
        (20.0, 4.0),  # 12 / 3
    ]


# ============================================================
# Test 3
# ============================================================

def test_all_entries_are_muon_hits():
    muon_number_dataframe = (
        ROOT.RDataFrame(5)
        .Define(
            "hasMuonHit",
            "true",
        )
    )

    muon_dataframe = ROOT.RDataFrame(20)

    result = calculate_entries_per_muon_hit(
        muon_dataframes=[muon_dataframe],
        muon_number_dataframes=[muon_number_dataframe],
        energies=[30.0],
    )

    # 20 entries / 5 hits
    assert result == [
        (30.0, 4.0),
    ]


# ============================================================
# Test 4
# ============================================================

def test_only_one_muon_hit():
    muon_number_dataframe = create_muon_dataframe(
        number_of_entries=10,
        hit_entries=[7],
    )

    muon_dataframe = ROOT.RDataFrame(25)

    result = calculate_entries_per_muon_hit(
        muon_dataframes=[muon_dataframe],
        muon_number_dataframes=[muon_number_dataframe],
        energies=[40.0],
    )

    # 25 / 1
    assert result == [
        (40.0, 25.0),
    ]


# ============================================================
# Test 5
# ============================================================

def test_fractional_ratio():
    muon_number_dataframe = create_muon_dataframe(
        number_of_entries=10,
        hit_entries=[0, 1, 2, 3],
    )

    muon_dataframe = ROOT.RDataFrame(10)

    result = calculate_entries_per_muon_hit(
        muon_dataframes=[muon_dataframe],
        muon_number_dataframes=[muon_number_dataframe],
        energies=[50.0],
    )

    # 10 / 4 = 2.5
    assert result == [
        (50.0, 2.5),
    ]


# ============================================================
# Test 6
# ============================================================

def test_zero_muon_hits():
    muon_number_dataframe = create_muon_dataframe(
        number_of_entries=5,
        hit_entries=[],
    )

    muon_dataframe = ROOT.RDataFrame(10)

    result = calculate_entries_per_muon_hit(
        muon_dataframes=[muon_dataframe],
        muon_number_dataframes=[muon_number_dataframe],
        energies=[60.0],
    )

    assert len(result) == 1

    assert result[0][0] == 60.0

    assert math.isnan(
        result[0][1]
    )


# ============================================================
# Test 7
# ============================================================

def test_empty_inputs():
    result = calculate_entries_per_muon_hit(
        muon_dataframes=[],
        muon_number_dataframes=[],
        energies=[],
    )

    assert result == []


# ============================================================
# Test 8
# ============================================================

def test_too_many_energies():
    muon_number_dataframe = create_muon_dataframe(
        number_of_entries=5,
        hit_entries=[0],
    )

    muon_dataframe = ROOT.RDataFrame(5)

    exception_was_raised = False

    try:
        calculate_entries_per_muon_hit(
            muon_dataframes=[
                muon_dataframe,
            ],
            muon_number_dataframes=[
                muon_number_dataframe,
            ],
            energies=[
                10.0,
                20.0,
            ],
        )

    except rangingError:
        exception_was_raised = True

    assert exception_was_raised


# ============================================================
# Test 9
# ============================================================

def test_too_many_muon_dataframes():
    muon_number_dataframe = create_muon_dataframe(
        number_of_entries=5,
        hit_entries=[0],
    )

    muon_dataframe_1 = ROOT.RDataFrame(5)
    muon_dataframe_2 = ROOT.RDataFrame(5)

    exception_was_raised = False

    try:
        calculate_entries_per_muon_hit(
            muon_dataframes=[
                muon_dataframe_1,
                muon_dataframe_2,
            ],
            muon_number_dataframes=[
                muon_number_dataframe,
            ],
            energies=[
                10.0,
            ],
        )

    except rangingError:
        exception_was_raised = True

    assert exception_was_raised


# ============================================================
# Test 10
# ============================================================

def test_too_many_muon_number_dataframes():
    muon_number_dataframe_1 = create_muon_dataframe(
        number_of_entries=5,
        hit_entries=[0],
    )

    muon_number_dataframe_2 = create_muon_dataframe(
        number_of_entries=5,
        hit_entries=[1],
    )

    muon_dataframe = ROOT.RDataFrame(5)

    exception_was_raised = False

    try:
        calculate_entries_per_muon_hit(
            muon_dataframes=[
                muon_dataframe,
            ],
            muon_number_dataframes=[
                muon_number_dataframe_1,
                muon_number_dataframe_2,
            ],
            energies=[
                10.0,
            ],
        )

    except rangingError:
        exception_was_raised = True

    assert exception_was_raised


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":

    tests = [
        test_single_dataframe,
        test_multiple_dataframes,
        test_all_entries_are_muon_hits,
        test_only_one_muon_hit,
        test_fractional_ratio,
        test_zero_muon_hits,
        test_empty_inputs,
        test_too_many_energies,
        test_too_many_muon_dataframes,
        test_too_many_muon_number_dataframes,
    ]

    for test in tests:
        test()
        print(
            f"PASSED: {test.__name__}"
        )

    print(
        f"\nAll {len(tests)} tests passed."
    )