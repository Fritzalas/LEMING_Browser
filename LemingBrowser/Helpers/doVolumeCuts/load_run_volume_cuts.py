from pathlib import Path
from typing import Optional
import os
import sys
import ROOT

current = os.path.dirname(
    os.path.realpath(__file__)
)
parent = os.path.dirname(
    current
)
sys.path.append(
    parent
)

from Exceptions.doVolumeCutsError import doVolumeCutsError
from doVolumeCuts.temporaryfiles import (
    register_volume_cut_file,
)
from doVolumeCuts.trambuildhelper import (
    get_local_project_directory,
    normalize_remote_absolute_path,
    request_ssh_password,
    prepare_volume_cuts_executable,
    prepare_remote_volume_cuts_executable,
    create_unique_output_file,
    create_remote_output_path,
    create_volume_cuts_command,
    execute_volume_cuts_command,
    execute_remote_volume_cuts_command,
    validate_output_file,
    delete_file_if_present,
)

from mount_and_load_data.mounting import (
    get_remote_target_directory,
    get_local_target_directory,
)
from Provenance.provenance import register_provenance

def load_run_volume_cuts(
    runspec: str,
    project_directory: str | Path,
    isRemoteProjectDirectory: bool,
    tree_name: str,
    host: str,
    user: str,
    local_directory: str | Path | None,
    remote_directory: str,
    output_file: str | Path,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    zmin: float,
    zmax: float,
    tmin: Optional[float],
    tmax: Optional[float],
    rebuild: bool,
    print_folder_summary: bool,
    number_of_threads: int | None,
    conda_base: str | Path,
    conda_environment: str,
):
    temporary_output_path: Path | None = None
    success = False

    try:
        if number_of_threads is None:
            number_of_threads = 1

        # ------------------------------------------------------------
        # Validate inputs.
        # ------------------------------------------------------------
        cleaned_runspec = _validate_inputs(
            runspec=runspec,
            project_directory=project_directory,
            tree_name=tree_name,
            local_directory=local_directory,
            remote_directory=remote_directory,
            output_file=output_file,
            xmin=xmin,
            xmax=xmax,
            ymin=ymin,
            ymax=ymax,
            zmin=zmin,
            zmax=zmax,
            tmin=tmin,
            tmax=tmax,
            number_of_threads=number_of_threads,
        )

        # ------------------------------------------------------------
        # ROOT multithreading applies to the local RDataFrame.
        # ------------------------------------------------------------
        ROOT.EnableImplicitMT(
            number_of_threads
        )

        print(
            f"ROOT implicit multithreading enabled "
            f"with {number_of_threads} threads."
        )

        # ============================================================
        # REMOTE PROJECT
        # ============================================================
        if isRemoteProjectDirectory:

            print(
                "Remote TRAM project detected."
            )

            # --------------------------------------------------------
            # IMPORTANT:
            #
            # The mounting helper expects:
            #
            #     data0/leming/...
            #
            # NOT:
            #
            #     /data0/leming/...
            #
            # Therefore project_directory is passed unchanged here.
            # --------------------------------------------------------
            mounted_project_path = (
                get_remote_target_directory(
                    host=host,
                    user=user,
                    remote_directory=str(
                        project_directory
                    ).lstrip("/"),
                    print_folder_summary=(
                        print_folder_summary
                    ),
                )
            )

            # --------------------------------------------------------
            # Native path as seen by the remote machine.
            #
            # This DOES require /data0/... (but the function if user is tired is there to help him and fix the correct dir :) )
            # --------------------------------------------------------
            remote_project_path = (
                normalize_remote_absolute_path(
                    project_directory
                )
            )

            # --------------------------------------------------------
            # A remotely executed tram_dovolumecuts cannot use a
            # directory that exists only on the local machine.
            # --------------------------------------------------------
            if local_directory is not None:
                raise doVolumeCutsError(
                    "local_directory cannot be used when "
                    "isRemoteProjectDirectory=True because "
                    "tram_dovolumecuts executes on the "
                    "remote machine."
                )

            # --------------------------------------------------------
            # Mount the ROOT input directory locally.
            #
            # This is useful for local visibility but is NOT passed
            # to tram_dovolumecuts.
            # --------------------------------------------------------
            mounted_input_directory = (
                get_remote_target_directory(
                    host=host,
                    user=user,
                    remote_directory=str(
                        remote_directory
                    ).lstrip("/"),
                    print_folder_summary=(
                        print_folder_summary
                    ),
                )
            )

            # Silence unused-variable warnings while retaining the mount operation deliberately.
            _ = mounted_input_directory

            # Native input path for the remote executable.
            remote_input_directory = (
                normalize_remote_absolute_path(
                    remote_directory
                )
            )

            # --------------------------------------------------------
            # Ask once for SSH password.
            # --------------------------------------------------------
            ssh_password = (
                request_ssh_password(
                    host=host,
                    user=user,
                )
            )

            # --------------------------------------------------------
            # Configure/build on the remote machine.
            # --------------------------------------------------------
            (
                remote_build_directory,
                remote_executable,
            ) = (
                prepare_remote_volume_cuts_executable(
                    project_directory=(
                        remote_project_path
                    ),
                    host=host,
                    user=user,
                    conda_base=conda_base,
                    conda_environment=(
                        conda_environment
                    ),
                    password=ssh_password,
                    rebuild=rebuild,
                )
            )

            _ = remote_build_directory

            # --------------------------------------------------------
            # Generate a unique filename through the mounted project.
            #
            # This gives us the local/GVFS representation:
            #
            # /run/user/.../gvfs/.../output_x.root
            # --------------------------------------------------------
            temporary_output_path = (
                create_unique_output_file(
                    output_file,
                    project_directory=(
                        mounted_project_path
                    ),
                    uuid_digits=10,
                )
            )

            # --------------------------------------------------------
            # Generate the equivalent native remote path:
            #
            # /data0/.../output_x.root
            # --------------------------------------------------------
            remote_output_path = (
                create_remote_output_path(
                    local_output_path=(
                        temporary_output_path
                    ),
                    remote_project_directory=(
                        remote_project_path
                    ),
                )
            )

            # --------------------------------------------------------
            # Build the command using ONLY native remote paths.
            # --------------------------------------------------------
            command = (
                create_volume_cuts_command(
                    executable=remote_executable,
                    input_directory=(
                        remote_input_directory
                    ),
                    runspec=cleaned_runspec,
                    output_file=(
                        remote_output_path
                    ),
                    xmin=xmin,
                    xmax=xmax,
                    ymin=ymin,
                    ymax=ymax,
                    zmin=zmin,
                    zmax=zmax,
                    tmin=tmin,
                    tmax=tmax,
                    number_of_threads=(
                        number_of_threads
                    ),
                )
            )

            # --------------------------------------------------------
            # Run remotely using the SAME password.
            # --------------------------------------------------------
            execute_remote_volume_cuts_command(
                command=command,
                host=host,
                user=user,
                conda_base=conda_base,
                conda_environment=(
                    conda_environment
                ),
                password=ssh_password,
            )

            input_directory_for_print = (
                remote_input_directory
            )

        # ============================================================
        # LOCAL PROJECT
        # ============================================================
        else:

            project_path = (
                get_local_project_directory(
                    project_directory
                )
            )

            # --------------------------------------------------------
            # Resolve input directory.
            # --------------------------------------------------------
            if local_directory is not None:

                input_directory = (
                    get_local_target_directory(
                        local_directory,
                        print_folder_summary=(
                            print_folder_summary
                        ),
                    )
                )

                print(
                    "Using local ROOT files."
                )

            else:

                input_directory = (
                    get_remote_target_directory(
                        host=host,
                        user=user,
                        remote_directory=str(
                            remote_directory
                        ).lstrip("/"),
                        print_folder_summary=(
                            print_folder_summary
                        ),
                    )
                )

            # --------------------------------------------------------
            # Local build.
            # --------------------------------------------------------
            (
                build_directory,
                executable,
            ) = (
                prepare_volume_cuts_executable(
                    project_path,
                    rebuild=rebuild,
                )
            )

            # --------------------------------------------------------
            # Local temporary output.
            # --------------------------------------------------------
            temporary_output_path = (
                create_unique_output_file(
                    output_file,
                    project_directory=(
                        project_path
                    ),
                    uuid_digits=10,
                )
            )

            # --------------------------------------------------------
            # Local command.
            # --------------------------------------------------------
            command = (
                create_volume_cuts_command(
                    executable=executable,
                    input_directory=(
                        input_directory
                    ),
                    runspec=cleaned_runspec,
                    output_file=(
                        temporary_output_path
                    ),
                    xmin=xmin,
                    xmax=xmax,
                    ymin=ymin,
                    ymax=ymax,
                    zmin=zmin,
                    zmax=zmax,
                    tmin=tmin,
                    tmax=tmax,
                    number_of_threads=(
                        number_of_threads
                    ),
                )
            )

            execute_volume_cuts_command(
                command=command,
                build_directory=(
                    build_directory
                ),
            )

            input_directory_for_print = (
                input_directory
            )

        # ============================================================
        # COMMON LOCAL SIDE
        # ============================================================

        # For a remote project this is the GVFS-mounted path pointing
        # to the ROOT file that was produced remotely.
        validate_output_file(
            temporary_output_path
        )

        dataframe = ROOT.RDataFrame(
            tree_name,
            str(
                temporary_output_path
            ),
        )

        volume_cut_parameters = {
            "runspec": cleaned_runspec,
            "tree_name": tree_name,

            "x_range": [
                xmin,
                xmax,
            ],
            "y_range": [
                ymin,
                ymax,
            ],
            "z_range": [
                zmin,
                zmax,
            ],
            "time_range": (
                [tmin, tmax]
                if tmin is not None or tmax is not None
                else None
            ),

            "number_of_threads": number_of_threads,

            "project_type": (
                "remote"
                if isRemoteProjectDirectory
                else "local"
            ),

            "project_directory": str(
                project_directory
            ),

            "input_directory": str(
                input_directory_for_print
            ),

            "backing_root_file": str(
                temporary_output_path
            ),
            "rebuild": rebuild,
        }


        if isRemoteProjectDirectory:
            volume_cut_parameters.update({
                "host": host,
                "user": user,
                "remote_directory": remote_directory,
            })

        register_provenance(
            dataframe,
            kind="dataframe",
            operation="TRAM volume cuts",
            parameters=volume_cut_parameters,
            parents=[],
        )

        register_volume_cut_file(
            temporary_output_path
        )

        success = True

        print(
            "\nVolume cuts completed."
        )

        print(
            f"Runs: {cleaned_runspec}"
        )

        print(
            f"Input directory: "
            f"{input_directory_for_print}"
        )

        print(
            f"Tree: {tree_name}"
        )

        print(
            f"Threads: {number_of_threads}"
        )

        print(
            f"Backing ROOT file: "
            f"{temporary_output_path}"
        )

        return dataframe

    finally:
        print(
            "doVolumeCuts Executed"
        )

        if not success:
            delete_file_if_present(
                temporary_output_path
            )

            print(
                "#########################################"
            )

            print(
                "An error occurred. Check your logs"
            )


def _validate_inputs(
    runspec: str,
    project_directory: str | Path,
    tree_name: str,
    local_directory: str | Path | None,
    remote_directory: str,
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
) -> str:
    """
    Validate all user inputs before starting any expensive operations.

    Returns
    -------
    str
        Cleaned run specification.
    """

    cleaned_runspec = _normalize_runspec(runspec)

    _validate_non_empty_path(
        project_directory,
        name="project_directory",
    )

    _validate_non_empty_string(
        tree_name,
        name="tree_name",
    )

    _validate_non_empty_path(
        output_file,
        name="output_file",
    )

    if local_directory is not None:
        _validate_non_empty_path(
            local_directory,
            name="local_directory",
        )
    else:
        _validate_non_empty_string(
            remote_directory,
            name="remote_directory",
        )

    _validate_volume_cuts(
        xmin=xmin,
        xmax=xmax,
        ymin=ymin,
        ymax=ymax,
        zmin=zmin,
        zmax=zmax,
        tmin=tmin,
        tmax=tmax,
    )

    _validate_number_of_threads(
        number_of_threads
    )

    return cleaned_runspec


def _validate_volume_cuts(
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    zmin: float,
    zmax: float,
    tmin: Optional[float],
    tmax: Optional[float],
) -> None:
    """
    Validate all spatial and temporal cut ranges.
    """

    _validate_cut_range(
        xmin,
        xmax,
        name="x",
    )

    _validate_cut_range(
        ymin,
        ymax,
        name="y",
    )

    _validate_cut_range(
        zmin,
        zmax,
        name="z",
    )

    _validate_cut_range(
        tmin,
        tmax,
        name="time",
    )


def _validate_cut_range(
    minimum: Optional[float],
    maximum: Optional[float],
    name: str,
) -> None:
    """
    Validate one optional minimum/maximum cut pair.
    """

    if minimum is not None and maximum is not None:
        if minimum > maximum:
            raise doVolumeCutsError(
                f"{name} minimum cannot be greater than "
                f"{name} maximum."
            )


def _normalize_runspec(
    runspec: str,
) -> str:
    """
    Return a cleaned, non-empty run specification.
    """

    if not isinstance(runspec, str):
        raise doVolumeCutsError(
            "runspec must be a string."
        )

    cleaned_runspec = runspec.strip()

    if not cleaned_runspec:
        raise doVolumeCutsError(
            "runspec cannot be empty."
        )

    return cleaned_runspec


def _validate_non_empty_string(
    value: str,
    name: str,
) -> None:
    """
    Validate that a value is a non-empty string.
    """

    if not isinstance(value, str):
        raise doVolumeCutsError(
            f"{name} must be a string."
        )

    if not value.strip():
        raise doVolumeCutsError(
            f"{name} cannot be empty."
        )


def _validate_non_empty_path(
    value: str | Path,
    name: str,
) -> None:
    """
    Validate that a path-like argument is not empty.
    """

    if not isinstance(value, (str, Path)):
        raise doVolumeCutsError(
            f"{name} must be a string or Path."
        )

    if not str(value).strip():
        raise doVolumeCutsError(
            f"{name} cannot be empty."
        )


def _get_available_threads() -> int:
    """
    Return the number of CPUs available to this process.

    On Linux, sched_getaffinity respects CPU restrictions from
    schedulers, containers, taskset, etc.

    Falls back to os.cpu_count() when CPU affinity information is
    unavailable.
    """

    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def _validate_number_of_threads(
    number_of_threads: int,
) -> None:
    """
    Validate the requested ROOT thread count.
    """

    # bool is a subclass of int, so explicitly reject it.
    if isinstance(number_of_threads, bool):
        raise doVolumeCutsError(
            "number_of_threads must be an integer."
        )

    if not isinstance(number_of_threads, int):
        raise doVolumeCutsError(
            "number_of_threads must be an integer."
        )

    if number_of_threads < 1:
        raise doVolumeCutsError(
            "number_of_threads must be at least 1."
        )

    available_threads = _get_available_threads()

    if number_of_threads > available_threads:
        raise doVolumeCutsError(
            f"number_of_threads cannot be greater than the "
            f"number of threads available to this process. "
            f"Requested: {number_of_threads}, "
            f"available: {available_threads}."
        )