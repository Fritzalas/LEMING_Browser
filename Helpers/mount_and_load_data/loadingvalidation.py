from pathlib import Path
import os
import sys
# getting the name of the directory
# where the this file is present.
current = os.path.dirname(os.path.realpath(__file__))
# Getting the parent directory name
# where the current directory is present.
parent = os.path.dirname(current)
# adding the parent directory to 
# the sys.path.
sys.path.append(parent)
from Exceptions.LoadError import LoadError
from Exceptions.InvalidRunSpecification import InvalidRunSpecification

def validate_resolve_root_files_arguments(
    directory: str | Path,
    runspec: str,
) -> Path:
    if not isinstance(directory, (str, Path)):
        raise LoadError(
            "'directory' must be a str or Path, "
            f"got {type(directory).__name__}."
        )

    directory = Path(directory)

    if not directory.is_dir():
        raise LoadError(
            f"Directory does not exist:\n{directory}"
        )

    if not isinstance(runspec, str):
        raise LoadError(
            "'runspec' must be a string, "
            f"got {type(runspec).__name__}."
        )

    if not runspec.strip():
        raise InvalidRunSpecification(
            "The run specification cannot be empty."
        )

    print("Loading Validation verified")

    return directory