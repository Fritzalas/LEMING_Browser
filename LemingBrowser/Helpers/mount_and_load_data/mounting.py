from getpass import getpass
import pexpect
import os
import sys
from pathlib import Path
from .mountingvalidation import (
    validate_remote_mount_arguments,
    validate_local_target_directory_arguments
)
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

def get_local_target_directory(
    local_directory: str | Path,
    print_folder_summary: bool,
) -> Path:
    validate_local_target_directory_arguments(
        local_directory=local_directory,
        print_folder_summary=print_folder_summary
    )
    target_directory = Path(local_directory).expanduser().resolve()

    if not target_directory.is_dir():
        raise MountError(
            "The local directory does not exist or cannot be accessed:\n"
            f"{target_directory}"
        )

    if print_folder_summary:
        _print_root_directory_summary(target_directory)

    return target_directory

def get_remote_target_directory(
    host: str,
    user: str,
    remote_directory: str,
    print_folder_summary: bool,
) -> Path:
    _mount_remote_directory_and_check_root_files(
        host = host,
        user = user,
        remote_directory = remote_directory,
        print_folder_summary = print_folder_summary
    )
    mount_directory = Path(
        f"/run/user/{os.getuid()}/gvfs/"
        f"sftp:host={host},user={user}"
    )
    target_directory = mount_directory / remote_directory

    if not target_directory.is_dir():
        raise MountError(
            "The remote directory is not mounted or cannot be accessed:\n"
            f"{target_directory}\n\n"
            "Run mount_and_check_root_files() first."
        )
    
    return target_directory

def _mount_remote_directory_and_check_root_files(
    host: str,
    user: str,
    remote_directory: str,
    print_folder_summary: bool,
) -> None:
    validate_remote_mount_arguments(
        host = host,
        user = user,
        remote_directory = remote_directory,
        print_folder_summary = print_folder_summary
    )
    sftp_url = f"sftp://{user}@{host}"

    mount_directory = Path(
        f"/run/user/{os.getuid()}/gvfs/"
        f"sftp:host={host},user={user}"
    )

    if mount_directory.is_dir():
        print(f"Already mounted: {sftp_url}", flush=True)

    else:
        print(f"Mounting {sftp_url} ...", flush=True)
        print("############ WARNING ############")
        print(
            "If this is the first time you are mounting this host, "
            "run the following command in a terminal first:"
        )
        print(f"/usr/bin/gio mount {sftp_url}")
        print("Enter your password when prompted:", flush=True)

        password = getpass(
            f"Password for {user}@{host}: "
        )

        process = None

        try:
            process = pexpect.spawn(
                "/usr/bin/gio",
                ["mount", sftp_url],
                encoding="utf-8",
                timeout=60,
            )

            while True:
                match = process.expect([
                    r"Password:",
                    r"Authentication Required",
                    pexpect.EOF,
                    pexpect.TIMEOUT,
                ])

                if match == 0:
                    process.sendline(password)

                elif match == 1:
                    continue

                elif match == 2:
                    break

                elif match == 3:
                    process.close(force=True)
                    raise MountError(
                        "Timed out while mounting the SFTP location."
                    )

        finally:
            password = None

        process.close()

        if not mount_directory.is_dir():
            raise MountError(
                f"Could not mount {sftp_url}.\n"
                f"gio exit status: {process.exitstatus}\n"
                f"Output: {process.before}"
            )

        print("Mounted successfully.", flush=True)

    target_directory = mount_directory / remote_directory

    if not target_directory.is_dir():
        raise MountError(
            "Directory does not exist or cannot be accessed:\n"
            f"{target_directory}"
        )

    if print_folder_summary:
        _print_root_directory_summary(
            target_directory=target_directory
        )

def _print_root_directory_summary(
    target_directory: Path,
) -> None:
    file_count = 0
    total_size = 0

    for path in target_directory.glob("*.root"):
        try:
            if path.is_file():
                file_count += 1
                total_size += path.stat().st_size
        except OSError as error:
            print(f"Could not inspect {path}: {error}")

    print(f"\nDirectory: {target_directory}")
    print(f"Number of .root files: {file_count}")
    print(f"Total size: {_format_size(total_size)}")
    print(f"Total size in bytes: {total_size:,}")

def _format_size(size_bytes: int) -> str:
    """Convert a byte count into a human-readable size."""
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    size = float(size_bytes)

    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024

    return f"{size_bytes} B"