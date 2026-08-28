from __future__ import annotations

import re
from pathlib import Path

ROOT_FILE_PATTERN = re.compile(
    r"^run(?P<run>\d{5})_(?P<subrun>\d{5}).*\.root$",
    re.IGNORECASE,
)

def scan_runs(directory: Path) -> dict[int, dict[int, list[Path]]]:
    """
    Scan the directory and return:

        {
            run_number: {
                subrun_number: [matching_files]
            }
        }
    """
    runs: dict[int, dict[int, list[Path]]] = {}

    for path in directory.iterdir():
        if not path.is_file():
            continue

        match = ROOT_FILE_PATTERN.match(path.name)
        if match is None:
            continue

        run_number = int(match.group("run"))
        subrun_number = int(match.group("subrun"))

        runs.setdefault(
            run_number,
            {}
        ).setdefault(
            subrun_number,
            []
        ).append(path)

    for subruns in runs.values():
        for paths in subruns.values():
            paths.sort()

    return runs


def get_latest_run_number(
    runs: dict[int, dict[int, list[Path]]]
) -> int | None:
    """
    Return the run that was updated most recently.

    The newest modification time of any file belonging
    to the run determines which run is latest.

    If two runs have exactly the same timestamp,
    the larger run number wins.
    """

    if not runs:
        return None

    def run_sort_key(
        run_number: int,
    ) -> tuple[float, int]:

        newest_mtime = max(
            path.stat().st_mtime
            for paths
            in runs[run_number].values()
            for path in paths
        )

        return (
            newest_mtime,
            run_number,
        )

    return max(
        runs,
        key=run_sort_key,
    )