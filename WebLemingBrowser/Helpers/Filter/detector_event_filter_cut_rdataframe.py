from __future__ import annotations

from itertools import count
from typing import Any
import os
import sys
import ROOT

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
if parent not in sys.path:
    sys.path.append(parent)

from CPP.load_detector_event_filter_helper import (
    declare_event_group_helper,
)
from Exceptions.FilterError import FilterError


_GROUP_FILTER_ID = count()

def apply_detector_event_filter_cut_rdataframe(
    dataframes: Any | list[Any],
    detectors: str | list[str],
    cut_filters: str | list[str],
    detector_column: str = "Idetname",
    event_column: str = "IEventNb",
    run_column: str = "Runnumber",
    subrun_column: str = "Subrunnumber",
) -> Any | list[Any]:   
    ############################################################################
    ############### Deprecated Function with the new tram files ################
    ############################################################################
    #****** Deprecated with the new loaf format ***********
    filtered_dataframes = detector_event_filter_cut_rdataframe(
        dataframes=dataframes,
        detectors=detectors,
        cut_filters=cut_filters,
        detector_column=detector_column,
        event_column=event_column,
        run_column=run_column,
        subrun_column=subrun_column
    )
    print("Detector Event filtering executed")
    return filtered_dataframes

def detector_event_filter_cut_rdataframe(
    dataframes: Any | list[Any],
    detectors: str | list[str],
    cut_filters: str | list[str],
    detector_column: str,
    event_column: str,
    run_column: str,
    subrun_column: str,
) -> Any | list[Any]:
    """Fast event-group detector filtering.
    ******* Deprecated with the new loaf format (per detector cut can happen with global filter) ***********
    An event is accepted only when every requested detector:

      * is present at least once; and
      * passes its cut on every matching row.

    Once an event is accepted, every row belonging to the same
    (run, subrun, event) key is retained.

    Performance characteristics
    ---------------------------
    The first pass:

      * hashes the detector name once per row;
      * performs one detector-table lookup;
      * dispatches the appropriate cut with an integer switch;
      * updates a slot-local event hash map.

    Finalization:

      * merges slot maps in-place;
      * discards rejected-event state;
      * stores accepted event keys in a compact sorted vector.

    The second pass performs binary search on that immutable vector.
    """
    single_dataframe = not isinstance(
        dataframes,
        (list, tuple),
    )

    input_dataframes = (
        [dataframes]
        if single_dataframe
        else list(dataframes)
    )

    detectors = (
        [detectors]
        if isinstance(detectors, str)
        else list(detectors)
    )

    cut_filters = (
        [cut_filters]
        if isinstance(cut_filters, str)
        else list(cut_filters)
    )

    # --------------------------------------------------------------
    # Validate input
    # --------------------------------------------------------------

    if len(detectors) != len(cut_filters):
        raise FilterError(
            "The number of detectors and cuts must match.\n"
            f"Detectors: {len(detectors)}\n"
            f"Cuts: {len(cut_filters)}"
        )

    if not detectors:
        return dataframes

    if len(detectors) > 64:
        raise FilterError(
            "detector_event_filter_cut_rdataframe supports "
            "at most 64 detector cuts per call."
        )

    normalized_detectors: list[str] = []
    normalized_cuts: list[str] = []

    for index, (detector, cut) in enumerate(
        zip(detectors, cut_filters),
        start=1,
    ):
        if not isinstance(detector, str):
            raise FilterError(
                f"Detector {index} must be a string."
            )

        if not isinstance(cut, str):
            raise FilterError(
                f"Cut {index} must be a string."
            )

        detector = detector.strip()
        cut = cut.strip()

        if not detector:
            raise FilterError(
                f"Detector {index} cannot be empty."
            )

        if not cut:
            raise FilterError(
                f"Cut {index} cannot be empty."
            )

        normalized_detectors.append(detector)
        normalized_cuts.append(cut)

    if (
        len(set(normalized_detectors))
        != len(normalized_detectors)
    ):
        raise FilterError(
            "Detector names must be unique for an "
            "event-group detector filter."
        )

    required_columns = {
        detector_column,
        event_column,
        run_column,
        subrun_column,
    }

    for dataframe_index, dataframe in enumerate(
        input_dataframes,
        start=1,
    ):
        available_columns = {
            str(column)
            for column in dataframe.GetColumnNames()
        }

        missing_columns = (
            required_columns
            -
            available_columns
        )

        if missing_columns:
            raise FilterError(
                "Required columns are missing.\n"
                f"Dataset: {dataframe_index}\n"
                "Missing: "
                + ", ".join(
                    sorted(missing_columns)
                )
            )

    # Generic helper is JIT-compiled only once per process.
    declare_event_group_helper()

    detector_cuts = [
        {
            "detector": detector,
            "cut": cut,
        }
        for detector, cut in zip(
            normalized_detectors,
            normalized_cuts,
        )
    ]

    contexts: list[dict[str, Any]] = []

    # --------------------------------------------------------------
    # Construct first-pass graphs
    # --------------------------------------------------------------

    for dataframe_index, dataframe in enumerate(
        input_dataframes,
        start=1,
    ):
        filter_id = next(_GROUP_FILTER_ID)

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
            .SmartDetectorEventFilter
            .CreateContext(
                filter_id,
                number_of_slots,
                len(normalized_detectors),
            )
        )

        if not context:
            raise FilterError(
                "Could not create detector-event "
                f"filter context {filter_id}."
            )

        # Register requested detectors once.
        #
        # DetectorIndex() can now perform:
        #
        #   string -> hash -> integer detector index
        #
        # rather than comparing the row against every detector string.
        try:
            for detector_index, detector in enumerate(
                normalized_detectors
            ):
                ROOT.SmartDetectorEventFilter.AddDetector(
                    context,
                    detector_index,
                    detector,
                )
        except Exception as exception:
            raise FilterError(
                "Could not initialize detector lookup "
                f"for dataset {dataframe_index}: "
                f"{exception}"
            ) from exception

        context_address = int(
            ROOT.addressof(context)
        )

        context_expression = (
            "reinterpret_cast<"
            "SmartDetectorEventFilter::Context*>"
            f"({context_address}ULL)"
        )

        # ----------------------------------------------------------
        # Generate one fused C++ expression.
        #
        # Important:
        #
        # DetectorIndex() hashes detector_column ONCE.
        #
        # switch() means only the matching detector's cut is
        # evaluated.
        #
        # No detector-index RDF column is created.
        # No cut-pass RDF column is created.
        # ----------------------------------------------------------

        detector_index_column = (
            "__detector_event_filter_detector_index_"
            f"{filter_id}"
        )

        observe_column = (
            "__detector_event_filter_observe_"
            f"{filter_id}"
        )

        # One detector hash lookup per row.
        scan_dataframe = dataframe.Define(
            detector_index_column,
            (
                "SmartDetectorEventFilter::DetectorIndex("
                f"{context_expression}, "
                f"{detector_column}"
                ")"
            ),
        )

        # Integer dispatch.
        #
        # Only the selected detector cut is evaluated because ?: evaluates
        # only its selected branch.
        observe_expression = "1ULL"

        for detector_index in reversed(
            range(len(normalized_cuts))
        ):
            cut = normalized_cuts[detector_index]

            observe_expression = (
                "("
                f"{detector_index_column} == {detector_index}"
                " ? "
                "SmartDetectorEventFilter::Observe("
                f"{context_expression}, "
                "rdfslot_, "
                f"{run_column}, "
                f"{subrun_column}, "
                f"{event_column}, "
                f"{detector_index}, "
                "SmartDetectorEventFilter::CutPass("
                f"({cut})"
                ")"
                ")"
                " : "
                f"{observe_expression}"
                ")"
            )

        scan_action = (
            scan_dataframe
            .Define(
                observe_column,
                observe_expression,
            )
            .Sum(observe_column)
        )

        contexts.append(
            {
                "input_dataframe": dataframe,
                "context": context,
                "context_expression": context_expression,
                "scan_action": scan_action,
                "dataframe_index": dataframe_index,
                "filter_id": filter_id,
            }
        )

    # --------------------------------------------------------------
    # Execute all first-pass graphs together.
    # --------------------------------------------------------------

    scan_actions = [
        item["scan_action"]
        for item in contexts
    ]

    try:
        ROOT.RDF.RunGraphs(scan_actions)

    except Exception:
        # Compatibility fallback for ROOT versions/builds where
        # RunGraphs() is unavailable or unreliable.
        for action in scan_actions:
            action.GetValue()

    # --------------------------------------------------------------
    # Merge slot maps and create compact accepted-event arrays.
    # --------------------------------------------------------------

    for item in contexts:
        ROOT.SmartDetectorEventFilter.Finalize(
            item["context"]
        )

    # --------------------------------------------------------------
    # Construct lazy second-pass filtered dataframes.
    # --------------------------------------------------------------

    output_dataframes: list[Any] = []

    for item in contexts:
        dataframe = item["input_dataframe"]

        context_expression = (
            item["context_expression"]
        )

        dataframe_index = (
            item["dataframe_index"]
        )

        filtered_dataframe = dataframe.Filter(
            (
                "SmartDetectorEventFilter::Accepted("
                f"{context_expression}, "
                f"{run_column}, "
                f"{subrun_column}, "
                f"{event_column}"
                ")"
            ),
            (
                f"Dataset {dataframe_index}, "
                "detector event-group filter"
            ),
        )

        # Keep references associated with the returned RDF graph.
        filtered_dataframe._detector_event_filter_context = (
            item["context"]
        )

        filtered_dataframe._detector_event_filter_context_id = (
            item["filter_id"]
        )

        output_dataframes.append(
            filtered_dataframe
        )

    if single_dataframe:
        return output_dataframes[0]

    return output_dataframes