from __future__ import annotations

from itertools import count
from typing import Any
import os
import sys
import ROOT

current = os.path.dirname(
    os.path.realpath(__file__)
)
parent = os.path.dirname(current)
if parent not in sys.path:
    sys.path.append(parent)

from Exceptions.CoincidenceError import CoincidenceError
from CPP.coincidence_loaf_old_helper import (
    declare_coincidence_loaf_old_helper,
)

_COINCIDENCE_OLD_ID = count()


def apply_loaf_coincidence_old(
   dataframes: Any | list[Any],
   detectors: list[str],
   detector_column: str = "Idetname",
   event_column: str = "IEventNb",
   run_column: str = "Runnumber",
   subrun_column: str = "Subrunnumber",
   time_column: str = "Itime",
) -> Any | list[Any]:
    ############################################################################
    ############### Deprecated Function with the new tram files ################
    ############################################################################
    #****** Deprecated with the new loaf format ***********
    coincidence_dataframes = coincidence_loaf_old(
        dataframes=dataframes,
        detectors=detectors,
        detector_column=detector_column,
        event_column=event_column,
        run_column=run_column,
        subrun_column=subrun_column,
        time_column=time_column
    )    
    print("Detectors Coincidence Applied")
    return coincidence_dataframes 

def coincidence_loaf_old(
    dataframes: Any | list[Any],
    detectors: list[str],
    detector_column: str,
    event_column: str,
    run_column: str,
    subrun_column: str,
    time_column: str,
) -> Any | list[Any]:
    """
    ****** Deprecated with the new loaf format ***********
    Add a `time_coinc` column to old-loaf RDataFrames.

    For every (run, subrun, event) group:

      * every requested detector must be present;
      * time_coinc is the average time of detectors[0] and detectors[1];
      * time_coinc is written only on the selected detectors[0] row;
      * every other row receives NaN;
      * groups missing any requested detector receive NaN everywhere.

    If detectors[0] or detectors[1] occurs multiple times in a group,
    the row with the smallest rdfentry_ is used.

    Parameters
    ----------
    dataframes:
        One ROOT.RDataFrame or a list/tuple of ROOT.RDataFrames.

    detectors:
        Detector names which must all occur in the event group.
        At least two unique detectors are required.

    detector_column:
        Column containing detector names.

    event_column:
        Event-number column.

    run_column:
        Run-number column.

    subrun_column:
        Subrun-number column.

    time_column:
        Time column.
    """

    # --------------------------------------------------------------
    # Normalize dataframe input
    # --------------------------------------------------------------

    single_dataframe = not isinstance(
        dataframes,
        (list, tuple),
    )

    input_dataframes = (
        [dataframes]
        if single_dataframe
        else list(dataframes)
    )

    if not input_dataframes:
        return dataframes

    # --------------------------------------------------------------
    # Validate detectors
    # --------------------------------------------------------------

    if isinstance(detectors, str):
        raise CoincidenceError(
            "detectors must contain at least two detector names."
        )

    try:
        detectors = list(detectors)
    except TypeError as exception:
        raise CoincidenceError(
            "detectors must be an iterable of detector names."
        ) from exception

    if len(detectors) < 2:
        raise CoincidenceError(
            "coincidence_loaf_old requires at least two detectors."
        )

    if len(detectors) > 64:
        raise CoincidenceError(
            "coincidence_loaf_old supports at most "
            "64 detectors per call."
        )

    normalized_detectors: list[str] = []

    for index, detector in enumerate(
        detectors,
        start=1,
    ):
        if not isinstance(detector, str):
            raise CoincidenceError(
                f"Detector {index} must be a string."
            )

        detector = detector.strip()

        if not detector:
            raise CoincidenceError(
                f"Detector {index} cannot be empty."
            )

        normalized_detectors.append(detector)

    if (
        len(set(normalized_detectors))
        !=
        len(normalized_detectors)
    ):
        raise CoincidenceError(
            "Detector names must be unique."
        )

    # --------------------------------------------------------------
    # Validate column names
    # --------------------------------------------------------------

    column_arguments = {
        "detector_column": detector_column,
        "event_column": event_column,
        "run_column": run_column,
        "subrun_column": subrun_column,
        "time_column": time_column,
    }

    for argument_name, column_name in column_arguments.items():
        if not isinstance(column_name, str):
            raise CoincidenceError(
                f"{argument_name} must be a string."
            )

        if not column_name.strip():
            raise CoincidenceError(
                f"{argument_name} cannot be empty."
            )

    # --------------------------------------------------------------
    # Validate dataframes
    # --------------------------------------------------------------

    required_columns = set(
        column_arguments.values()
    )

    for dataframe_index, dataframe in enumerate(
        input_dataframes,
        start=1,
    ):
        try:
            available_columns = {
                str(column)
                for column in dataframe.GetColumnNames()
            }
        except Exception as exception:
            raise CoincidenceError(
                f"Dataset {dataframe_index} is not a valid "
                "ROOT RDataFrame."
            ) from exception

        missing_columns = (
            required_columns
            -
            available_columns
        )

        if missing_columns:
            raise CoincidenceError(
                "Required columns are missing.\n"
                f"Dataset: {dataframe_index}\n"
                "Missing: "
                + ", ".join(
                    sorted(missing_columns)
                )
            )

        if "time_coinc" in available_columns:
            raise CoincidenceError(
                f"Dataset {dataframe_index} already "
                "contains a time_coinc column."
            )

    # --------------------------------------------------------------
    # Declare optimized C++ helper once
    # --------------------------------------------------------------

    declare_coincidence_loaf_old_helper()

    contexts: list[dict[str, Any]] = []

    # --------------------------------------------------------------
    # First pass
    #
    # ObserveRow:
    #   * performs detector lookup;
    #   * immediately rejects irrelevant detector rows;
    #   * updates the per-slot event map for relevant rows.
    #
    # Using it directly as an RDF Filter means Count() forces
    # evaluation without needing an artificial Define + Sum.
    # --------------------------------------------------------------

    for dataframe in input_dataframes:
        coincidence_id = next(
            _COINCIDENCE_OLD_ID
        )

        try:
            number_of_slots = max(
                1,
                int(dataframe.GetNSlots()),
            )
        except Exception:
            number_of_slots = max(
                1,
                int(ROOT.GetThreadPoolSize()),
            )

        context = (
            ROOT
            .CoincidenceLoafOld
            .CreateContext(
                coincidence_id,
                number_of_slots,
                len(normalized_detectors),
            )
        )

        if not context:
            raise CoincidenceError(
                "Could not create coincidence context "
                f"{coincidence_id}."
            )

        try:
            for detector_index, detector in enumerate(
                normalized_detectors
            ):
                ROOT.CoincidenceLoafOld.AddDetector(
                    context,
                    detector_index,
                    detector,
                )

        except Exception:
            ROOT.CoincidenceLoafOld.DestroyContext(
                coincidence_id
            )
            raise

        context_address = int(
            ROOT.addressof(context)
        )

        context_expression = (
            "reinterpret_cast<"
            "CoincidenceLoafOld::Context*>"
            f"({context_address}ULL)"
        )

        scan_action = (
            dataframe
            .Filter(
                (
                    "CoincidenceLoafOld::ObserveRow("
                    f"{context_expression}, "
                    "rdfslot_, "
                    f"{detector_column}, "
                    f"{run_column}, "
                    f"{subrun_column}, "
                    f"{event_column}, "
                    f"{time_column}, "
                    "rdfentry_"
                    ")"
                )
            )
            .Count()
        )

        contexts.append(
            {
                "input_dataframe": dataframe,
                "context": context,
                "context_expression":
                    context_expression,
                "scan_action": scan_action,
                "coincidence_id":
                    coincidence_id,
            }
        )

    # --------------------------------------------------------------
    # Execute all first-pass scans together
    # --------------------------------------------------------------

    scan_actions = [
        item["scan_action"]
        for item in contexts
    ]

    try:
        ROOT.RDF.RunGraphs(
            scan_actions
        )

    except Exception:
        # Compatibility fallback for ROOT versions where
        # RunGraphs does not accept these result pointers.
        for action in scan_actions:
            action.GetValue()

    # --------------------------------------------------------------
    # Finalize
    #
    # This merges the per-slot maps and produces:
    #
    #     rdfentry_ -> time_coinc
    #
    # Only successful coincidence rows are stored.
    # --------------------------------------------------------------

    try:
        for item in contexts:
            ROOT.CoincidenceLoafOld.Finalize(
                item["context"]
            )

    except Exception:
        for item in contexts:
            try:
                ROOT.CoincidenceLoafOld.DestroyContext(
                    item["coincidence_id"]
                )
            except Exception:
                pass

        raise

    # Second Pass
    # The helper directly looks up:
    #
    #   rdfentry_ -> double
    #
    # --------------------------------------------------------------

    output_dataframes: list[Any] = []

    for item in contexts:
        parent_dataframe = item["input_dataframe"]

        output_dataframe = parent_dataframe.Define(
            "time_coinc",
            (
                "CoincidenceLoafOld::CoincidenceTime("
                f"{item['context_expression']}, "
                "rdfentry_"
                ")"
            ),
        )

        # Keep the PyROOT proxy/context information associated with
        # the lazy output graph.
        output_dataframe._coincidence_old_context = (
            item["context"]
        )

        output_dataframe._coincidence_old_context_id = (
            item["coincidence_id"]
        )

        output_dataframes.append(
            output_dataframe
        )

    if single_dataframe:
        return output_dataframes[0]

    return output_dataframes