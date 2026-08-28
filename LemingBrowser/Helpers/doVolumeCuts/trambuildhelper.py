from pathlib import Path
from typing import Optional
import getpass
import secrets
import shlex
import subprocess
import paramiko
from Exceptions.TramBuildError import TramBuildError


# =====================================================================
# TRAM PROJECT BUILD HELPERS
# =====================================================================


# ---------------------------------------------------------------------
# PATH HELPERS
# ---------------------------------------------------------------------


def normalize_remote_absolute_path(
    path: str | Path,
) -> Path:
    """
    Convert a remote path into an absolute path as seen by the
    remote machine.

    Examples
    --------
    data0/leming/project
        ->
    /data0/leming/project

    /data0/leming/project
        ->
    /data0/leming/project
    """
    path_text = str(path).strip()

    if not path_text:
        raise TramBuildError(
            "Remote path cannot be empty."
        )

    if not path_text.startswith("/"):
        path_text = "/" + path_text

    return Path(path_text)


def get_local_project_directory(
    project_directory: str | Path,
) -> Path:
    """
    Return a validated absolute local project directory.

    The directory must contain CMakeLists.txt.
    """
    project_path = (
        Path(project_directory)
        .expanduser()
        .resolve()
    )

    if not project_path.is_dir():
        raise TramBuildError(
            "Project directory does not exist:\n"
            f"{project_path}"
        )

    cmake_file = project_path / "CMakeLists.txt"

    if not cmake_file.is_file():
        raise TramBuildError(
            "The project directory does not contain "
            "CMakeLists.txt:\n"
            f"{cmake_file}"
        )

    return project_path


# ---------------------------------------------------------------------
# LOCAL BUILD HELPERS
# ---------------------------------------------------------------------


def _get_or_create_build_directory(
    project_directory: Path,
) -> tuple[Path, bool]:
    """
    Return the local project's build directory.

    Returns
    -------
    tuple[pathlib.Path, bool]
        Build directory and whether it was newly created.
    """
    build_directory = project_directory / "build"

    if build_directory.exists():
        if not build_directory.is_dir():
            raise TramBuildError(
                "The build path exists but is not a directory:\n"
                f"{build_directory}"
            )

        return build_directory, False

    print(
        f"Creating build directory:\n"
        f"{build_directory}"
    )

    build_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    return build_directory, True


def _configure_cmake_project(
    build_directory: Path,
    force: bool = False,
) -> None:
    """
    Configure a local CMake project.
    """
    cmake_cache = build_directory / "CMakeCache.txt"

    if cmake_cache.is_file() and not force:
        print("CMake project is already configured.")
        return

    print("\nConfiguring project with CMake...")

    subprocess.run(
        [
            "cmake",
            "..",
        ],
        cwd=build_directory,
        check=True,
    )


def _build_cmake_project(
    build_directory: Path,
) -> None:
    """
    Build a local CMake project.
    """
    print("\nBuilding project...")

    subprocess.run(
        [
            "cmake",
            "--build",
            ".",
        ],
        cwd=build_directory,
        check=True,
    )


def prepare_volume_cuts_executable(
    project_directory: Path,
    executable_name: str = "tram_dovolumecuts",
    rebuild: bool = False,
) -> tuple[Path, Path]:
    """
    Prepare the local tram_dovolumecuts executable.
    """
    build_directory, build_was_created = (
        _get_or_create_build_directory(
            project_directory
        )
    )

    _configure_cmake_project(
        build_directory,
        force=False,
    )

    executable = (
        build_directory
        / executable_name
    )

    if (
        build_was_created
        or rebuild
        or not executable.is_file()
    ):
        _build_cmake_project(
            build_directory
        )

    if not executable.is_file():
        raise TramBuildError(
            "The project was built, but the executable "
            "was not found:\n"
            f"{executable}"
        )

    return (
        build_directory,
        executable,
    )


# ---------------------------------------------------------------------
# REMOTE SSH HELPERS
# ---------------------------------------------------------------------


def request_ssh_password(
    host: str,
    user: str,
) -> str:
    """
    Prompt interactively for an SSH password.

    getpass hides the entered password.
    """
    return getpass.getpass(
        prompt=f"SSH password for {user}@{host}: "
    )


def _create_remote_environment_command(
    command: str,
    conda_base: str | Path,
    conda_environment: str,
) -> str:
    """
    Wrap a remote command so it executes inside the requested
    Conda environment.
    """
    conda_script = (
        Path(conda_base)
        / "etc"
        / "profile.d"
        / "conda.sh"
    )

    return (
        f"source {shlex.quote(str(conda_script))}"
        f" && conda activate "
        f"{shlex.quote(conda_environment)}"
        f" && {command}"
    )


def execute_remote_shell_command(
    command: str,
    host: str,
    user: str,
    conda_base: str | Path,
    conda_environment: str,
    password: str,
) -> None:
    """
    Execute a command remotely through SSH using Paramiko.

    The command is run inside the selected Conda environment.
    """
    environment_command = (
        _create_remote_environment_command(
            command=command,
            conda_base=conda_base,
            conda_environment=conda_environment,
        )
    )

    print("\nRunning remote command:")
    print(environment_command)
    print()

    client = paramiko.SSHClient()

    client.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )

    try:
        client.connect(
            hostname=host,
            username=user,
            password=password,
        )

        _, stdout, stderr = client.exec_command(
            environment_command
        )

        # Stream stdout while the command is running.
        for line in iter(stdout.readline, ""):
            print(
                line,
                end="",
            )

        exit_status = (
            stdout.channel.recv_exit_status()
        )

        error_text = (
            stderr.read()
            .decode(errors="replace")
        )

        if error_text:
            print(
                error_text,
                end="",
            )

        if exit_status != 0:
            raise TramBuildError(
                "Remote command failed.\n"
                f"Host: {user}@{host}\n"
                f"Exit status: {exit_status}\n"
                f"Command:\n"
                f"{environment_command}"
            )

    finally:
        client.close()


# ---------------------------------------------------------------------
# REMOTE BUILD HELPERS
# ---------------------------------------------------------------------


def prepare_remote_volume_cuts_executable(
    project_directory: str | Path,
    host: str,
    user: str,
    conda_base: str | Path,
    conda_environment: str,
    password: str,
    executable_name: str = "tram_dovolumecuts",
    rebuild: bool = False,
) -> tuple[Path, Path]:
    """
    Configure and build tram_dovolumecuts on the remote machine.

    Returned paths are native REMOTE paths, not GVFS paths.
    """
    project_directory = (
        normalize_remote_absolute_path(
            project_directory
        )
    )

    build_directory = (
        project_directory
        / "build"
    )

    executable = (
        build_directory
        / executable_name
    )

    project_q = shlex.quote(
        str(project_directory)
    )

    build_q = shlex.quote(
        str(build_directory)
    )

    executable_q = shlex.quote(
        str(executable)
    )

    commands = [
        (
            f"test -f "
            f"{project_q}/CMakeLists.txt"
        ),
        (
            f"mkdir -p "
            f"{build_q}"
        ),
    ]

    if rebuild:
        commands.extend(
            [
                (
                    f"rm -f "
                    f"{build_q}/CMakeCache.txt"
                ),
                (
                    f"cmake "
                    f"-S {project_q} "
                    f"-B {build_q}"
                ),
            ]
        )

    else:
        commands.append(
            (
                f"if [ ! -f "
                f"{build_q}/CMakeCache.txt ]; then "
                f"cmake "
                f"-S {project_q} "
                f"-B {build_q}; "
                f"fi"
            )
        )

    # Always invoke the build.
    # CMake performs its own incremental build checking.
    commands.append(
        f"cmake --build {build_q}"
    )

    commands.append(
        (
            f"if [ ! -x {executable_q} ]; then "
            f"echo 'tram_dovolumecuts was not created "
            f"or is not executable' >&2; "
            f"exit 1; "
            f"fi"
        )
    )

    remote_command = (
        " && ".join(commands)
    )

    execute_remote_shell_command(
        command=remote_command,
        host=host,
        user=user,
        conda_base=conda_base,
        conda_environment=conda_environment,
        password=password,
    )

    return (
        build_directory,
        executable,
    )


# ---------------------------------------------------------------------
# OUTPUT PATH HELPERS
# ---------------------------------------------------------------------


def _resolve_output_file(
    output_file: str | Path,
    project_directory: Path,
) -> Path:
    """
    Resolve an output path on the LOCAL/mounted filesystem.

    Relative output files are interpreted relative to the project
    directory.
    """
    output_path = (
        Path(output_file)
        .expanduser()
    )

    if not output_path.is_absolute():
        output_path = (
            project_directory
            / output_path
        )

    output_path = (
        output_path.resolve()
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return output_path


def create_unique_output_file(
    output_file: str | Path,
    project_directory: Path,
    uuid_digits: int = 10,
) -> Path:
    """
    Create a unique LOCAL/mounted output filename.

    The file itself is not created.
    """
    if uuid_digits < 1:
        raise TramBuildError(
            "uuid_digits must be at least 1."
        )

    base_output_path = (
        _resolve_output_file(
            output_file,
            project_directory=project_directory,
        )
    )

    if (
        base_output_path.suffix.lower()
        != ".root"
    ):
        raise TramBuildError(
            "The volume-cut output filename "
            "must end with .root:\n"
            f"{base_output_path}"
        )

    maximum_value = (
        10 ** uuid_digits
    )

    for _ in range(100):
        numeric_uuid = (
            f"{secrets.randbelow(maximum_value):0{uuid_digits}d}"
        )

        unique_output_path = (
            base_output_path.with_name(
                f"{base_output_path.stem}_"
                f"{numeric_uuid}"
                f"{base_output_path.suffix}"
            )
        )

        if not unique_output_path.exists():
            return unique_output_path

    raise TramBuildError(
        "Could not generate an unused "
        "temporary output filename."
    )


def create_remote_output_path(
    local_output_path: Path,
    remote_project_directory: str | Path,
) -> Path:
    """
    Return the native remote counterpart of a mounted output path.

    Only the filename is copied from the local/mounted path.
    """
    remote_project_directory = (
        normalize_remote_absolute_path(
            remote_project_directory
        )
    )

    return (
        remote_project_directory
        / local_output_path.name
    )


# ---------------------------------------------------------------------
# COMMAND CONSTRUCTION
# ---------------------------------------------------------------------


def _append_optional_cut(
    command: list[str],
    option: str,
    value: Optional[float],
) -> None:
    """
    Append an optional numerical command-line argument.
    """
    if value is not None:
        command.extend(
            [
                option,
                str(value),
            ]
        )


def create_volume_cuts_command(
    executable: str | Path,
    input_directory: str | Path,
    runspec: str,
    output_file: str | Path,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    zmin: float,
    zmax: float,
    tmin: Optional[float],
    tmax: Optional[float],
    number_of_threads: int,
) -> list[str]:
    """
    Build the tram_dovolumecuts command.
    """
    command = [
        str(executable),
        "--input-directory",
        str(input_directory),
        "--runs",
        runspec,
        "-o",
        str(output_file),
        "-x",
        str(xmin),
        "-X",
        str(xmax),
        "-y",
        str(ymin),
        "-Y",
        str(ymax),
        "-z",
        str(zmin),
        "-Z",
        str(zmax),
        "-j",
        str(number_of_threads),
    ]

    _append_optional_cut(
        command,
        option="-t",
        value=tmin,
    )

    _append_optional_cut(
        command,
        option="-T",
        value=tmax,
    )

    return command


def _print_command(
    command: list[str],
) -> None:
    """
    Print a shell-readable command.
    """
    print("\nRunning volume cuts:")
    print(
        shlex.join(command)
    )
    print()


# ---------------------------------------------------------------------
# LOCAL / REMOTE EXECUTION
# ---------------------------------------------------------------------


def execute_volume_cuts_command(
    command: list[str],
    build_directory: Path,
) -> None:
    """
    Execute tram_dovolumecuts locally.
    """
    _print_command(
        command
    )

    subprocess.run(
        command,
        cwd=build_directory,
        check=True,
    )


def execute_remote_volume_cuts_command(
    command: list[str],
    host: str,
    user: str,
    conda_base: str | Path,
    conda_environment: str,
    password: str,
) -> None:
    """
    Execute tram_dovolumecuts on the remote machine.

    All paths in command must be native remote paths.
    """
    _print_command(
        command
    )

    remote_command = (
        shlex.join(command)
    )

    execute_remote_shell_command(
        command=remote_command,
        host=host,
        user=user,
        conda_base=conda_base,
        conda_environment=conda_environment,
        password=password,
    )


# ---------------------------------------------------------------------
# OUTPUT VALIDATION / CLEANUP
# ---------------------------------------------------------------------


def validate_output_file(
    output_file: Path,
) -> None:
    """
    Confirm that an output file is visible locally.

    For remote projects this should be the GVFS-mounted representation.
    """
    if not output_file.is_file():
        raise TramBuildError(
            "tram_dovolumecuts finished without "
            "reporting an error, but the output "
            "file was not found:\n"
            f"{output_file}"
        )


def delete_file_if_present(
    file_path: str | Path | None,
) -> None:
    """
    Delete a local or GVFS-mounted file if it exists.
    """
    if file_path is None:
        return

    path = Path(
        file_path
    )

    try:
        path.unlink(
            missing_ok=True
        )

    except TypeError:
        try:
            if path.exists():
                path.unlink()

        except OSError as error:
            print(
                "Warning: could not delete "
                "temporary file:\n"
                f"{path}\n"
                f"{error}"
            )

    except OSError as error:
        print(
            "Warning: could not delete "
            "temporary file:\n"
            f"{path}\n"
            f"{error}"
        )