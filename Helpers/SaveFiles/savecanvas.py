######################## Save-file-format helper ########################

from pathlib import Path
from typing import Any, Iterable
import os
import sys
import ROOT

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from Exceptions.SaveFileError import SaveFileError


_FORMAT_ALIASES = {
    "tif": "tiff",
    "tiff": "tiff",
}


_SUPPORTED_FORMATS = {
    "pdf",
    "png",
    "svg",
    "tiff",
    "gif",
    "bmp",
    "ps",
    "eps",
    "root",
    "c",
}


def save_canvas(
    output_filename: str | Path | None,
    output_formats: str | Iterable[str],
    canvas: Any,
) -> list[Path]:
    """
    Save one or more ROOT canvases in one or more formats.

    `canvas` may be either:

        ROOT.TCanvas

    or the canvas-info dictionary returned by plot_loaf_histo().

    Both 1D and 2D canvases are saved automatically.

    For ROOT output, the TCanvas itself is written to the ROOT file.

    Returns
    -------
    list[Path]
        Paths of all successfully written files.
    """

    if output_filename is None:
        return []

    if canvas is None:
        raise SaveFileError(
            "canvas cannot be None."
        )

    # ---------------------------------------------------------
    # Normalize output formats
    # ---------------------------------------------------------

    if isinstance(output_formats, str):
        requested_formats = [output_formats]
    else:
        requested_formats = list(output_formats)

    if not requested_formats:
        raise SaveFileError(
            "At least one output format must be provided."
        )

    normalized_formats: list[str] = []

    for output_format in requested_formats:

        if not isinstance(output_format, str):
            raise SaveFileError(
                "Every output format must be a string."
            )

        normalized_format = (
            output_format
            .strip()
            .lower()
            .lstrip(".")
        )

        normalized_format = _FORMAT_ALIASES.get(
            normalized_format,
            normalized_format,
        )

        if normalized_format not in _SUPPORTED_FORMATS:

            supported = ", ".join(
                sorted(_SUPPORTED_FORMATS)
            )

            raise SaveFileError(
                f"Unsupported output format "
                f"{output_format!r}. "
                f"Supported formats: {supported}."
            )

        if normalized_format not in normalized_formats:
            normalized_formats.append(
                normalized_format
            )

    # ---------------------------------------------------------
    # Normalize canvases
    # ---------------------------------------------------------

    canvases: list[tuple[Any, str | None]] = []

    # Direct TCanvas
    if (
        hasattr(canvas, "InheritsFrom")
        and canvas.InheritsFrom("TCanvas")
    ):
        canvases.append(
            (canvas, None)
        )

    # canvas_info dictionary from plot_loaf_histo()
    elif isinstance(canvas, dict):

        # 1D canvas
        canvas_1d = canvas.get("canvas")

        if canvas_1d is not None:
            canvases.append(
                (
                    canvas_1d,
                    canvas.get("canvas_name"),
                )
            )

        # 2D canvases
        for item in canvas.get(
            "canvas_data_2d",
            [],
        ):
            canvas_2d = item.get("canvas")

            if canvas_2d is None:
                continue

            canvases.append(
                (
                    canvas_2d,
                    item.get("canvas_name"),
                )
            )

    else:
        raise SaveFileError(
            "canvas must be a ROOT TCanvas or "
            "a canvas-info dictionary."
        )

    if not canvases:
        raise SaveFileError(
            "No canvases were found to save."
        )

    # ---------------------------------------------------------
    # Output base
    # ---------------------------------------------------------

    output_base = Path(output_filename)

    if output_base.suffix:
        output_base = output_base.with_suffix("")

    output_base.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    saved_paths: list[Path] = []

    # ---------------------------------------------------------
    # Save every canvas
    # ---------------------------------------------------------

    multiple_canvases = len(canvases) > 1

    for canvas_index, (
        current_canvas,
        canvas_name,
    ) in enumerate(
        canvases,
        start=1,
    ):

        current_canvas.Modified()
        current_canvas.Update()

        # -----------------------------------------------------
        # Filename
        # -----------------------------------------------------

        if multiple_canvases:

            if canvas_name:
                safe_canvas_name = _make_safe_filename(
                    str(canvas_name)
                )

                current_base = (
                    output_base.parent
                    / f"{output_base.name}_{safe_canvas_name}"
                )

            else:
                current_base = (
                    output_base.parent
                    / f"{output_base.name}_{canvas_index}"
                )

        else:
            current_base = output_base

        # -----------------------------------------------------
        # Formats
        # -----------------------------------------------------

        for output_format in normalized_formats:

            output_path = current_base.with_suffix(
                f".{output_format}"
            )

            if output_format == "root":

                root_file = ROOT.TFile(
                    str(output_path),
                    "RECREATE",
                )

                if (
                    not root_file
                    or root_file.IsZombie()
                ):
                    raise SaveFileError(
                        f"Could not create ROOT file: "
                        f"{output_path}"
                    )

                try:
                    root_file.cd()

                    current_canvas.Write()

                finally:
                    root_file.Close()

            else:

                current_canvas.Print(
                    str(output_path),
                    output_format,
                )

            saved_paths.append(
                output_path
            )

            print(
                f"Saved canvas to {output_path}"
            )

    return saved_paths


def _make_safe_filename(
    name: str,
) -> str:
    """
    Make a canvas name safe for use in a filename.
    """

    safe_name = "".join(
        character
        if character.isalnum()
        or character in ("_", "-")
        else "_"
        for character in name
    )

    safe_name = safe_name.strip("_")

    return safe_name or "canvas"