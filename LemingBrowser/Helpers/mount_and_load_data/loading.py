from pathlib import Path
import os
import sys
import re

from .loadingvalidation import (
    validate_resolve_root_files_arguments
)
from .mounting import (
    get_remote_target_directory,
    get_local_target_directory,
)
# getting the name of the directory
# where this file is present.
current = os.path.dirname(
    os.path.realpath(__file__)
)
# Getting the parent directory name
# where the current directory is present.
parent = os.path.dirname(current)
# adding the parent directory to sys.path.
if parent not in sys.path:
    sys.path.append(parent)

from Exceptions.LoadError import LoadError
from Exceptions.InvalidRunSpecification import (
    InvalidRunSpecification
)
from Provenance.provenance import (
    register_provenance
)

def load_local_resolved_root_files(
    runspec: str,
    local_directory: str,
    print_folder_summary: bool,
):
    """
    Resolve a run specification against a local directory.

    Provenance is attached to the returned file list so later
    RDataFrames can trace their history back to the original
    run specification.
    """

    target_directory = get_local_target_directory(
        local_directory=local_directory,
        print_folder_summary=print_folder_summary,
    )

    selected_files = _resolve_root_files_from_runspec(
        directory=target_directory,
        runspec=runspec,
    )

    register_provenance(
        selected_files,
        kind="files",
        operation="local ROOT file selection",
        parameters={
            "runspec": runspec,
            "directory": str(
                target_directory
            ),
            "number_of_files": len(
                selected_files
            ),
            "files": [
                path.name
                for path in selected_files
            ],
        },
        parents=[],
    )

    return selected_files


def load_remote_resolved_root_files(
    runspec: str,
    host: str,
    user: str,
    remote_directory: str,
    print_folder_summary: bool,
):
    """
    Resolve a run specification against a remote directory.

    Provenance is attached to the returned file list so later
    RDataFrames can trace their history back to the original
    remote run specification.
    """

    target_directory = get_remote_target_directory(
        host=host,
        user=user,
        remote_directory=remote_directory,
        print_folder_summary=print_folder_summary,
    )

    selected_files = _resolve_root_files_from_runspec(
        directory=target_directory,
        runspec=runspec,
    )

    register_provenance(
        selected_files,
        kind="files",
        operation="remote ROOT file selection",
        parameters={
            "runspec": runspec,
            "host": host,
            "user": user,
            "remote_directory": remote_directory,
            "resolved_directory": str(
                target_directory
            ),
            "number_of_files": len(
                selected_files
            ),
            "files": [
                path.name
                for path in selected_files
            ],
        },
        parents=[],
    )

    return selected_files

def _resolve_root_files_from_runspec(
    directory: Path,
    runspec: str,
) -> list[Path]:
    """
    Convert a run specification into a list of existing ROOT files.

    The directory is scanned only once. All subsequent matching is
    performed locally in Python.
    """
    directory = validate_resolve_root_files_arguments(
        directory=directory,
        runspec=runspec,
    )

    # -------------------------------------------------------------
    # Scan the directory ONCE.
    # -------------------------------------------------------------

    root_files = sorted(
        path
        for path in directory.iterdir()
        if path.name.lower().endswith(".root")
    )

    # Index files by run and by (run, subrun).
    files_by_run: dict[int, list[Path]] = {}
    files_by_subrun: dict[tuple[int, int], list[Path]] = {}

    filename_pattern = re.compile(
        r"^run(\d{5})_(\d{5}).*\.root$",
        re.IGNORECASE,
    )

    for path in root_files:
        match = filename_pattern.match(path.name)

        if match is None:
            continue

        run_number = int(match.group(1))
        subrun_number = int(match.group(2))

        files_by_run.setdefault(
            run_number,
            [],
        ).append(path)

        files_by_subrun.setdefault(
            (run_number, subrun_number),
            [],
        ).append(path)

    # -------------------------------------------------------------
    # Resolve runspec using the in-memory index.
    # -------------------------------------------------------------

    selected_files: list[Path] = []
    missing_patterns: list[str] = []

    def add_exact_file(
        run_number: int,
        subrun_number: int,
    ) -> None:
        matches = files_by_subrun.get(
            (run_number, subrun_number)
        )

        if matches:
            selected_files.extend(matches)
        else:
            missing_patterns.append(
                f"run{run_number:05d}_{subrun_number:05d}*"
            )

    def add_complete_run(
        run_number: int,
    ) -> None:
        matches = files_by_run.get(run_number)

        if matches:
            selected_files.extend(matches)
        else:
            missing_patterns.append(
                f"run{run_number:05d}_*"
            )

    def add_run_from_subrun(
        run_number: int,
        first_subrun: int,
    ) -> None:
        """
        Add all existing files from first_subrun to the end
        of the given run.
        """
        found = False

        for (run, subrun), matches in files_by_subrun.items():
            if run == run_number and subrun >= first_subrun:
                selected_files.extend(matches)
                found = True

        if not found:
            missing_patterns.append(
                f"run{run_number:05d}_{first_subrun:05d}-*"
            )

    def add_run_until_subrun(
        run_number: int,
        last_subrun: int,
    ) -> None:
        """
        Add all existing files from the beginning of the run
        through last_subrun.
        """
        found = False

        for (run, subrun), matches in files_by_subrun.items():
            if run == run_number and subrun <= last_subrun:
                selected_files.extend(matches)
                found = True

        if not found:
            missing_patterns.append(
                f"run{run_number:05d}_*-{last_subrun:05d}"
            )

    # Remove spaces so e.g. "3442 - 3467" works.
    normalized_runspec = runspec.replace(" ", "")

    for token in normalized_runspec.split(","):
        if not token:
            raise InvalidRunSpecification(
                f"Empty selection in runspec: {runspec!r}"
            )

        token = token.removeprefix("run")

        token = re.sub(
            r"\.root$",
            "",
            token,
            flags=re.IGNORECASE,
        )

        token = re.sub(
            r"\.mid$",
            "",
            token,
            flags=re.IGNORECASE,
        )

        # ---------------------------------------------------------
        # Case 1: subrun range
        #
        # Same run:
        #   03442_00007-03442_00021
        #   03442_00007-00021
        #
        # Cross-run:
        #   03500_00007-03561_00004
        # ---------------------------------------------------------

        if "-" in token and "_" in token:
            left, right = token.split("-", 1)

            if "_" not in left:
                raise InvalidRunSpecification(
                    f"Invalid subrun range: {token!r}"
                )

            left_run_text, left_subrun_text = left.split(
                "_",
                1,
            )

            if "_" in right:
                right_run_text, right_subrun_text = right.split(
                    "_",
                    1,
                )
            else:
                right_run_text = left_run_text
                right_subrun_text = right

            try:
                left_run = int(left_run_text)
                right_run = int(right_run_text)
                left_subrun = int(left_subrun_text)
                right_subrun = int(right_subrun_text)

            except ValueError as error:
                raise InvalidRunSpecification(
                    f"Non-numeric subrun range: {token!r}"
                ) from error

            # -------------------------------------------------
            # Normalize reversed ranges.
            #
            # Example:
            #   3561_00004-3500_00007
            #
            # becomes:
            #   3500_00007-3561_00004
            # -------------------------------------------------

            left_endpoint = (
                left_run,
                left_subrun,
            )

            right_endpoint = (
                right_run,
                right_subrun,
            )

            if left_endpoint > right_endpoint:
                (
                    left_run,
                    right_run,
                ) = (
                    right_run,
                    left_run,
                )

                (
                    left_subrun,
                    right_subrun,
                ) = (
                    right_subrun,
                    left_subrun,
                )

            # -------------------------------------------------
            # Same-run subrun range
            # -------------------------------------------------

            if left_run == right_run:
                for subrun_number in range(
                    left_subrun,
                    right_subrun + 1,
                ):
                    add_exact_file(
                        left_run,
                        subrun_number,
                    )

            # -------------------------------------------------
            # Cross-run subrun range
            #
            # Example:
            #
            # 3500_00007-3561_00004
            #
            # means:
            #
            # 3500: subrun 7 -> end
            # 3501-3560: complete runs
            # 3561: beginning -> subrun 4
            # -------------------------------------------------

            else:
                add_run_from_subrun(
                    run_number=left_run,
                    first_subrun=left_subrun,
                )

                for run_number in range(
                    left_run + 1,
                    right_run,
                ):
                    add_complete_run(run_number)

                add_run_until_subrun(
                    run_number=right_run,
                    last_subrun=right_subrun,
                )

        # ---------------------------------------------------------
        # Case 2: exact subrun
        # ---------------------------------------------------------

        elif "_" in token:
            try:
                run_text, subrun_text = token.split(
                    "_",
                    1,
                )

                run_number = int(run_text)
                subrun_number = int(subrun_text)

            except ValueError as error:
                raise InvalidRunSpecification(
                    f"Invalid subrun: {token!r}"
                ) from error

            add_exact_file(
                run_number,
                subrun_number,
            )

        # ---------------------------------------------------------
        # Case 3: complete run range
        # ---------------------------------------------------------

        elif "-" in token:
            left, right = token.split("-", 1)

            try:
                first_run = int(left)
                last_run = int(right)

            except ValueError as error:
                raise InvalidRunSpecification(
                    f"Invalid run range: {token!r}"
                ) from error

            if first_run > last_run:
                first_run, last_run = (
                    last_run,
                    first_run,
                )

            for run_number in range(
                first_run,
                last_run + 1,
            ):
                add_complete_run(run_number)

        # ---------------------------------------------------------
        # Case 4: one complete run
        # ---------------------------------------------------------

        else:
            try:
                run_number = int(token)

            except ValueError as error:
                raise InvalidRunSpecification(
                    f"Invalid run number: {token!r}"
                ) from error

            add_complete_run(run_number)

    # -------------------------------------------------------------
    # Deduplicate and sort.
    # -------------------------------------------------------------

    selected_files = sorted(set(selected_files))

    print("\n" + "=" * 78)
    print(f"Run specification: {runspec}")
    print(f"Directory:         {directory}")
    print(f"Selected files:    {len(selected_files)}")
    print("-" * 78)

    for index, path in enumerate(
        selected_files,
        start=1,
    ):
        print(f"{index:4d}: {path.name}")

    print("=" * 78)

    if missing_patterns:
        print(
            "\nWarning: these files or patterns "
            "were not found:"
        )

        for item in missing_patterns:
            print(f"  {item}")

    if not selected_files:
        raise LoadError(
            f"No ROOT files matched run specification {runspec!r}"
        )

    return selected_files