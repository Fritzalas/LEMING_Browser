from pathlib import Path
from threading import Lock


_VOLUME_CUT_FILES: set[Path] = set()
_VOLUME_CUT_FILES_LOCK = Lock()


def register_volume_cut_file(
    file_path: str | Path,
) -> None:
    """
    Register a temporary ROOT file created by tram_dovolumecuts.
    """
    path = Path(file_path).expanduser().resolve()

    with _VOLUME_CUT_FILES_LOCK:
        _VOLUME_CUT_FILES.add(path)


def unregister_volume_cut_file(
    file_path: str | Path,
) -> None:
    """
    Remove a file from the registry without deleting it.
    """
    path = Path(file_path).expanduser().resolve()

    with _VOLUME_CUT_FILES_LOCK:
        _VOLUME_CUT_FILES.discard(path)


def get_registered_volume_cut_files() -> tuple[Path, ...]:
    """
    Return a snapshot of all registered volume-cut files.
    """
    with _VOLUME_CUT_FILES_LOCK:
        return tuple(_VOLUME_CUT_FILES)


def delete_registered_volume_cut_files() -> None:
    """
    Delete all temporary ROOT files created by tram_dovolumecuts
    during this Python session.

    Files that no longer exist are silently removed from the registry.
    Cleanup failures are reported but do not stop cleanup of other files.
    """
    with _VOLUME_CUT_FILES_LOCK:
        files = tuple(_VOLUME_CUT_FILES)

    for path in files:
        try:
            path.unlink(missing_ok=True)

        except TypeError:
            # Compatibility with older Python versions.
            try:
                if path.exists():
                    path.unlink()

            except OSError as error:
                print(
                    "Warning: could not delete volume-cut file:\n"
                    f"{path}\n"
                    f"{error}"
                )
                continue

        except OSError as error:
            print(
                "Warning: could not delete volume-cut file:\n"
                f"{path}\n"
                f"{error}"
            )
            continue

        with _VOLUME_CUT_FILES_LOCK:
            _VOLUME_CUT_FILES.discard(path)

        print(
            f"Deleted temporary volume-cut file:\n"
            f"{path}"
        )