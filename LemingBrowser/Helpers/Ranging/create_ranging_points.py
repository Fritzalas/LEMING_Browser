from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from Exceptions.rangingError import rangingError

def calculate_entries_per_muon_hit(
    muon_dataframes: list,
    muon_number_dataframes: list,
    energies: list[float],
) -> list[tuple[float, float]]:
    """
    Calculate the number of time entries per muon hit
    for each energy.

    Returns
    -------
    list[tuple[float, float]]
        Each tuple is:
            (energy, number_of_entries / number_of_muon_hits)
    """

    if not (
        len(muon_number_dataframes)
        == len(muon_dataframes)
        == len(energies)
    ):
        raise rangingError(
            "muon_dataframes, time_dataframes, and energies "
            "must have the same length."
        )

    results = []

    for energy, muon_dataframe, time_dataframe in zip(
        energies,
        muon_number_dataframes,
        muon_dataframes,
    ):
        # Number of events with a muon hit
        number_of_muon_hits = int(
            muon_dataframe
            .Filter("hasMuonEntranceHit == 1")
            .Count()
            .GetValue()
        )

        # Number of entries in the corresponding time dataframe
        number_of_entries = int(
            time_dataframe
            .Count()
            .GetValue()
        )

        if number_of_muon_hits == 0:
            ratio = float("nan")
        else:
            ratio = (
                number_of_entries
                / number_of_muon_hits
            )

        results.append(
            (energy, ratio)
        )

    return results