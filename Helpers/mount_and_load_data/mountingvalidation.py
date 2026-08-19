import os
import sys
from pathlib import Path
# getting the name of the directory
# where the this file is present.
current = os.path.dirname(os.path.realpath(__file__))
# Getting the parent directory name
# where the current directory is present.
parent = os.path.dirname(current)
# adding the parent directory to 
# the sys.path.
sys.path.append(parent)
from Exceptions.MountError import MountError

def validate_remote_mount_arguments(
    host: str,
    user: str,
    remote_directory: str,
    print_folder_summary: bool,
) -> None:
    string_arguments = {
        "host": host,
        "user": user,
        "remote_directory": remote_directory,
    }

    for name, value in string_arguments.items():
        if not isinstance(value, str):
            raise MountError(
                f"'{name}' must be a string, got {type(value).__name__}."
            )

        if not value.strip():
            raise MountError(
                f"'{name}' cannot be empty."
            )

    if not isinstance(print_folder_summary, bool):
        raise MountError(
            "'print_folder_summary' must be a bool, "
            f"got {type(print_folder_summary).__name__}."
        )

    print("Input Mounting data verified")

def validate_local_target_directory_arguments(
    local_directory: str | Path,
    print_folder_summary: bool,
) -> None:
    if not isinstance(local_directory, (str, Path)):
        raise MountError(
            "'local_directory' must be a str or Path, "
            f"got {type(local_directory).__name__}."
        )

    if isinstance(local_directory, str) and not local_directory.strip():
        raise MountError(
            "'local_directory' cannot be empty."
        )

    if not isinstance(print_folder_summary, bool):
        raise MountError(
            "'print_folder_summary' must be a bool, "
            f"got {type(print_folder_summary).__name__}."
        )