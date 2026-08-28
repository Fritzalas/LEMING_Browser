from pathlib import Path
from typing import Any
import os
import sys
import json
import ROOT
###############################################################################
ROOT.TH1.SetDefaultSumw2()
###############################################################################
import re
import time
import numpy as np
from collections.abc import Mapping, Sequence
# getting the name of the directory
# where the this file is present.
current = os.path.dirname(os.path.realpath(__file__))
# Getting the parent directory name
# where the current directory is present.
parent = os.path.dirname(current)
# adding the parent directory to 
# the sys.path.
sys.path.append(parent)
from Exceptions.HistogramError import HistogramError
from Classes.TramQuantitySpec import TramQuantitySpec
from Histograms.validatetramhisto import validate_create_tram_histograms_arguments

def get_tram_histograms(
    dataframe: Any | list[Any],
    dataframe_labels: list[str],
    quantities: str | list[str],
    bins: int | list[int | None] | None = None,
    ranges: (
        tuple[float, float]
        | list[float]
        | list[tuple[float, float] | list[float] | None]
        | None
    ) = None,
    histogram_config_filename: str | Path = (
        "tram_histogram_defaults.json"
    ),
    saveHistograms: bool = False,
    outputFileName: str = None
):
    all_histograms = create_tram_histograms(
        dataframe=dataframe,
        dataframe_labels=dataframe_labels,
        quantities=quantities,
        bins=bins,
        ranges=ranges,
        histogram_config_filename=histogram_config_filename,
        saveHistograms=saveHistograms,
        outputFileName = outputFileName
    )
    return all_histograms

def create_tram_histograms(
    dataframe: Any | list[Any],
    dataframe_labels: list[str],
    quantities: str | list[str],
    bins,
    ranges,
    histogram_config_filename: str | Path,
    saveHistograms: bool, #This is a variable where at the end every histo is saved at a specific root file
    outputFileName: str
):
    """
    Create tram 1D and 2D histograms.

    All ROOT actions are booked before event-loop execution so
    each dataframe is processed as efficiently as possible.
    """
    validate_create_tram_histograms_arguments(
        dataframe=dataframe,
        dataframe_labels=dataframe_labels,
        quantities=quantities,
        bins=bins,
        ranges=ranges,
        histogram_config_filename=histogram_config_filename,
    )

    dataframes = _normalize_dataframes(dataframe)

    labels = _normalize_dataframe_labels(
        dataframe_labels=dataframe_labels,
        dataframe_count=len(dataframes),
    )

    quantity_specs = _get_tram_quantities(
        quantities
    )

    required_columns = _get_required_columns(
        quantity_specs
    )

    _validate_dataframe_columns(
        dataframes=dataframes,
        required_columns=required_columns,
        mode_name="tram histogram creation",
    )

    histogram_config = _load_tram_histogram_defaults(
        histogram_config_filename
    )

    one_dimensional_specs = [
        spec
        for spec in quantity_specs
        if spec.dimension == 1
    ]

    two_dimensional_specs = [
        spec
        for spec in quantity_specs
        if spec.dimension == 2
    ]

    # ---------------------------------------------------------
    # Resolve which columns actually need automatic settings.
    #
    # IMPORTANT:
    # Book auto-statistics for ALL missing columns first, then
    # execute them together. This avoids one full event loop per
    # auto-ranged/auto-binned column.
    # ---------------------------------------------------------

    automatic_columns = _get_automatic_histogram_columns(
        all_quantity_specs=quantity_specs,
        one_dimensional_specs=one_dimensional_specs,
        two_dimensional_specs=two_dimensional_specs,
        bins=bins,
        ranges=ranges,
        config=histogram_config,
    )

    automatic_settings = (
        _calculate_automatic_histogram_settings_batch(
            dataframes=dataframes,
            columns=automatic_columns,
        )
        if automatic_columns
        else {}
    )

    # ---------------------------------------------------------
    # Resolve all histogram settings BEFORE booking histograms.
    # ---------------------------------------------------------

    one_dimensional_bins = (
        [
            setting
            for spec, setting in zip(quantity_specs, bins)
            if spec.dimension == 1
        ]
        if isinstance(bins, list)
        else bins
    )

    one_dimensional_ranges = (
        [
            setting
            for spec, setting in zip(quantity_specs, ranges)
            if spec.dimension == 1
        ]
        if isinstance(ranges, list)
        else ranges
    )

    one_dimensional_settings = (
        _prepare_1d_settings(
            quantity_specs=one_dimensional_specs,
            bins=one_dimensional_bins,
            ranges=one_dimensional_ranges,
            config=histogram_config,
            automatic_settings=automatic_settings,
        )
        if one_dimensional_specs
        else {}
    )

    two_dimensional_settings = (
        _prepare_2d_settings(
            all_quantity_specs=quantity_specs,
            two_dimensional_specs=two_dimensional_specs,
            bins=bins,
            ranges=ranges,
            config=histogram_config,
            automatic_settings=automatic_settings,
        )
        if two_dimensional_specs
        else {}
    )

    # ---------------------------------------------------------
    # Book EVERYTHING before executing ROOT.
    # ---------------------------------------------------------

    (
        count_results,
        histogram_jobs_1d,
        histogram_jobs_2d,
        result_handles,
    ) = _book_histogram_actions(
        dataframes=dataframes,
        dataframe_labels=labels,
        one_dimensional_specs=one_dimensional_specs,
        two_dimensional_specs=two_dimensional_specs,
        one_dimensional_settings=one_dimensional_settings,
        two_dimensional_settings=two_dimensional_settings,
    )

    # ---------------------------------------------------------
    # Execute all booked computation graphs.
    # ---------------------------------------------------------

    if result_handles:
        start_time = time.perf_counter()

        ROOT.RDF.RunGraphs(
            result_handles
        )

        elapsed = time.perf_counter() - start_time

        print(
            f"\nROOT histogram event loops completed "
            f"in {elapsed:.3f} s."
        )

    # ---------------------------------------------------------
    # Results are already computed now.
    # GetValue() does not need to rescan the dataset.
    # ---------------------------------------------------------

    entry_counts = {
        dataframe_index: int(
            result.GetValue()
        )
        for dataframe_index, result
        in count_results.items()
    }

    histogram_data_1d = _collect_1d_histograms(
        jobs=histogram_jobs_1d,
        entry_counts=entry_counts,
    )

    histogram_data_2d = _collect_2d_histograms(
        jobs=histogram_jobs_2d,
        entry_counts=entry_counts,
    )

    histogram_result = {
        "quantity_specs": quantity_specs,
        "histogram_data_1d": histogram_data_1d,
        "histogram_data_2d": histogram_data_2d,
        "histogram_data": (
            histogram_data_1d
            + histogram_data_2d
        ),
    }

    return _index_tram_histograms(
        histogram_data_1d=(
            histogram_result["histogram_data_1d"]
        ),
        histogram_data_2d=(
            histogram_result["histogram_data_2d"]
        ),
    )

def _book_histogram_actions(
    dataframes: list[Any],
    dataframe_labels: list[str],
    one_dimensional_specs: list[TramQuantitySpec],
    two_dimensional_specs: list[TramQuantitySpec],
    one_dimensional_settings: dict,
    two_dimensional_settings: dict,
):
    count_results = {}

    histogram_jobs_1d = []
    histogram_jobs_2d = []

    result_handles = []

    for dataframe_index, (
        dataframe,
        dataframe_label,
    ) in enumerate(
        zip(
            dataframes,
            dataframe_labels,
        ),
        start=1,
    ):
        # -----------------------------------------------------
        # ONE Count() per dataframe.
        # -----------------------------------------------------

        count_result = dataframe.Count()

        count_results[dataframe_index] = (
            count_result
        )

        result_handles.append(
            count_result
        )

        # -----------------------------------------------------
        # Book all 1D histograms.
        # -----------------------------------------------------

        for spec in one_dimensional_specs:
            assert spec.column is not None

            quantity = spec.column

            (
                bin_count,
                histogram_range,
            ) = one_dimensional_settings[
                quantity
            ]

            minimum, maximum = (
                histogram_range
            )

            histogram_name = (
                _make_tram_histogram_name(
                    quantity,
                    dataframe_index,
                )
            )

            histogram_title = (
                f"{quantity} Distribution;"
                f"{quantity};Entries"
            )

            histogram_result = (
                dataframe.Histo1D(
                    (
                        histogram_name,
                        histogram_title,
                        bin_count,
                        minimum,
                        maximum,
                    ),
                    quantity,
                )
            )

            result_handles.append(
                histogram_result
            )

            histogram_jobs_1d.append({
                "result": histogram_result,
                "quantity": quantity,
                "dataset_index": dataframe_index,
                "dataset_label": dataframe_label,
                "minimum": minimum,
                "maximum": maximum,
                "bins": bin_count,
                # provenance parent
                "dataframe": dataframe,
            })

        # -----------------------------------------------------
        # Book all 2D histograms.
        # -----------------------------------------------------

        for spec in two_dimensional_specs:
            assert spec.x_column is not None
            assert spec.y_column is not None

            (
                x_bins,
                x_minimum,
                x_maximum,
                y_bins,
                y_minimum,
                y_maximum,
            ) = two_dimensional_settings[
                spec.expression
            ]

            histogram_name = (
                _make_tram_2d_histogram_name(
                    spec,
                    dataframe_index,
                )
            )

            histogram_title = (
                f"{spec.y_column} versus "
                f"{spec.x_column};"
                f"{spec.x_column};"
                f"{spec.y_column}"
            )

            histogram_result = (
                dataframe.Histo2D(
                    (
                        histogram_name,
                        histogram_title,
                        x_bins,
                        x_minimum,
                        x_maximum,
                        y_bins,
                        y_minimum,
                        y_maximum,
                    ),
                    spec.x_column,
                    spec.y_column,
                )
            )

            result_handles.append(
                histogram_result
            )

            histogram_jobs_2d.append({
                "result": histogram_result,
                "spec": spec,
                "expression": spec.expression,
                "dimension": 2,
                "dataset_index": dataframe_index,
                "dataset_label": dataframe_label,
                "x_bins": x_bins,
                "x_minimum": x_minimum,
                "x_maximum": x_maximum,
                "y_bins": y_bins,
                "y_minimum": y_minimum,
                "y_maximum": y_maximum,
                # provenance parent
                "dataframe": dataframe,
            })

    return (
        count_results,
        histogram_jobs_1d,
        histogram_jobs_2d,
        result_handles,
    )

def _collect_1d_histograms(
    jobs: list[dict[str, Any]],
    entry_counts: dict[int, int],
) -> list[dict[str, Any]]:
    histogram_data = []

    for job in jobs:
        dataset_index = job[
            "dataset_index"
        ]

        entries = entry_counts[
            dataset_index
        ]

        if entries == 0:
            raise HistogramError(
                "No entries were found for dataset "
                f"{job['dataset_label']!r}."
            )

        histogram = (
            job["result"].GetValue()
        )

        histogram.SetDirectory(0)
        histogram.SetLineWidth(2)

        histogram_data.append({
            **job,
            "histogram": histogram,
            "entries": entries,
        })

        print(
            f"{job['dataset_label']} | "
            f"{job['quantity']} | "
            f"{entries} rows | "
            f"{int(histogram.GetEntries())} entries"
        )

    return histogram_data

def _collect_2d_histograms(
    jobs: list[dict[str, Any]],
    entry_counts: dict[int, int],
) -> list[dict[str, Any]]:
    histogram_data = []

    for job in jobs:
        dataset_index = job[
            "dataset_index"
        ]

        entries = entry_counts[
            dataset_index
        ]

        if entries == 0:
            raise HistogramError(
                "No entries were found for dataset "
                f"{job['dataset_label']!r}."
            )

        histogram = (
            job["result"].GetValue()
        )

        histogram.SetDirectory(0)

        histogram_data.append({
            **job,
            "histogram": histogram,
            "entries": entries,
        })

        print(
            f"{job['dataset_label']} | "
            f"{job['expression']} | "
            f"{entries} rows | "
            f"{int(histogram.GetEntries())} entries"
        )

    return histogram_data

def _prepare_2d_settings(
    all_quantity_specs: list[TramQuantitySpec],
    two_dimensional_specs: list[TramQuantitySpec],
    bins,
    ranges,
    config: dict[str, Any],
    automatic_settings: dict[
        str,
        tuple[int, tuple[float, float]],
    ],
) -> dict[
    str,
    tuple[
        int,
        float,
        float,
        int,
        float,
        float,
    ],
]:
    bin_settings = _get_tram_2d_bins(
        quantity_specs=all_quantity_specs,
        bins=bins,
    )

    range_settings = _get_tram_2d_ranges(
        quantity_specs=all_quantity_specs,
        ranges=ranges,
    )

    settings = {}

    # Avoid resolving the same column configuration repeatedly.
    column_defaults = {}

    def get_column_defaults(column: str):
        if column not in column_defaults:
            column_defaults[column] = (
                _resolve_tram_column_defaults(
                    column=column,
                    config=config,
                )
            )

        return column_defaults[column]

    def get_automatic_column_settings(
        column: str,
    ):
        try:
            return automatic_settings[column]
        except KeyError as error:
            raise HistogramError(
                f"Internal error: automatic histogram settings "
                f"for {column!r} were not precomputed."
            ) from error

    for spec in two_dimensional_specs:
        assert spec.x_column is not None
        assert spec.y_column is not None

        default_x_bins, default_x_range = (
            get_column_defaults(spec.x_column)
        )

        default_y_bins, default_y_range = (
            get_column_defaults(spec.y_column)
        )

        explicit_x_bins, explicit_y_bins = (
            bin_settings.get(
                spec.expression,
                (None, None),
            )
        )

        explicit_x_range, explicit_y_range = (
            range_settings.get(
                spec.expression,
                (None, None),
            )
        )

        x_bins = (
            explicit_x_bins
            if explicit_x_bins is not None
            else default_x_bins
        )

        y_bins = (
            explicit_y_bins
            if explicit_y_bins is not None
            else default_y_bins
        )

        x_range = (
            explicit_x_range
            if explicit_x_range is not None
            else default_x_range
        )

        y_range = (
            explicit_y_range
            if explicit_y_range is not None
            else default_y_range
        )

        if x_bins is None or x_range is None:
            (
                automatic_x_bins,
                automatic_x_range,
            ) = get_automatic_column_settings(
                    spec.x_column
                )

            if x_bins is None:
                x_bins = automatic_x_bins

            if x_range is None:
                x_range = automatic_x_range


        if y_bins is None or y_range is None:
            (
                automatic_y_bins,
                automatic_y_range,
            ) = get_automatic_column_settings(
                    spec.y_column
                )

            if y_bins is None:
                y_bins = automatic_y_bins

            if y_range is None:
                y_range = automatic_y_range

        x_minimum, x_maximum = x_range
        y_minimum, y_maximum = y_range

        settings[spec.expression] = (
            x_bins,
            x_minimum,
            x_maximum,
            y_bins,
            y_minimum,
            y_maximum,
        )
        print(
            f"tram histogram 2D: {spec.expression}, "
            f"x: bins={x_bins}, range=({x_minimum:g}, {x_maximum:g}), "
            f"y: bins={y_bins}, range=({y_minimum:g}, {y_maximum:g})"
        )

    return settings

def _prepare_1d_settings(
    quantity_specs: list[TramQuantitySpec],
    bins,
    ranges,
    config: dict[str, Any],
    automatic_settings: dict[
        str,
        tuple[int, tuple[float, float]],
    ],
) -> dict[str, tuple[int, tuple[float, float]]]:
    quantities = [
        spec.column
        for spec in quantity_specs
        if spec.column is not None
    ]

    bin_counts, histogram_ranges = (
        _resolve_tram_histogram_settings(
            quantities=quantities,
            bins=bins,
            ranges=ranges,
            config=config,
        )
    )

    for index, quantity in enumerate(quantities):
        bin_count = bin_counts[index]
        histogram_range = histogram_ranges[index]

        if bin_count is None or histogram_range is None:
            try:
                (
                    automatic_bins,
                    automatic_range,
                ) = automatic_settings[quantity]
            except KeyError as error:
                raise HistogramError(
                    f"Internal error: automatic histogram settings "
                    f"for {quantity!r} were not precomputed."
                ) from error

            if bin_count is None:
                bin_counts[index] = automatic_bins

            if histogram_range is None:
                histogram_ranges[index] = automatic_range

    return {
        quantity: (
            bin_count,
            histogram_range,
        )
        for (
            quantity,
            bin_count,
            histogram_range,
        ) in zip(
            quantities,
            bin_counts,
            histogram_ranges,
        )
    }

def _get_automatic_histogram_columns(
    all_quantity_specs: list[TramQuantitySpec],
    one_dimensional_specs: list[TramQuantitySpec],
    two_dimensional_specs: list[TramQuantitySpec],
    bins,
    ranges,
    config: dict[str, Any],
) -> list[str]:
    """
    Return each physical column that still needs bins and/or range
    after explicit arguments and JSON defaults have been applied.

    A column appears at most once even when it is used by both 1D
    and 2D histograms.
    """
    required: set[str] = set()

    one_dimensional_quantities = [
        spec.column
        for spec in one_dimensional_specs
        if spec.column is not None
    ]

    if one_dimensional_quantities:
        one_dimensional_bins = (
            [
                setting
                for spec, setting in zip(all_quantity_specs, bins)
                if spec.dimension == 1
            ]
            if isinstance(bins, list)
            else bins
        )

        one_dimensional_ranges = (
            [
                setting
                for spec, setting in zip(all_quantity_specs, ranges)
                if spec.dimension == 1
            ]
            if isinstance(ranges, list)
            else ranges
        )

        bin_counts, histogram_ranges = (
            _resolve_tram_histogram_settings(
                quantities=one_dimensional_quantities,
                bins=one_dimensional_bins,
                ranges=one_dimensional_ranges,
                config=config,
                emit_log=False,
            )
        )

        for quantity, bin_count, histogram_range in zip(
            one_dimensional_quantities,
            bin_counts,
            histogram_ranges,
        ):
            if bin_count is None or histogram_range is None:
                required.add(quantity)

    if two_dimensional_specs:
        bin_settings = _get_tram_2d_bins(
            quantity_specs=all_quantity_specs,
            bins=bins,
        )

        range_settings = _get_tram_2d_ranges(
            quantity_specs=all_quantity_specs,
            ranges=ranges,
        )

        column_defaults: dict[
            str,
            tuple[int | None, tuple[float, float] | None],
        ] = {}

        def defaults_for(column: str):
            if column not in column_defaults:
                column_defaults[column] = (
                    _resolve_tram_column_defaults(
                        column=column,
                        config=config,
                    )
                )
            return column_defaults[column]

        for spec in two_dimensional_specs:
            assert spec.x_column is not None
            assert spec.y_column is not None

            explicit_x_bins, explicit_y_bins = (
                bin_settings.get(
                    spec.expression,
                    (None, None),
                )
            )

            explicit_x_range, explicit_y_range = (
                range_settings.get(
                    spec.expression,
                    (None, None),
                )
            )

            default_x_bins, default_x_range = (
                defaults_for(spec.x_column)
            )
            default_y_bins, default_y_range = (
                defaults_for(spec.y_column)
            )

            x_bins = (
                explicit_x_bins
                if explicit_x_bins is not None
                else default_x_bins
            )
            y_bins = (
                explicit_y_bins
                if explicit_y_bins is not None
                else default_y_bins
            )
            x_range = (
                explicit_x_range
                if explicit_x_range is not None
                else default_x_range
            )
            y_range = (
                explicit_y_range
                if explicit_y_range is not None
                else default_y_range
            )

            if x_bins is None or x_range is None:
                required.add(spec.x_column)

            if y_bins is None or y_range is None:
                required.add(spec.y_column)

    # Stable ordering makes logs and tests deterministic.
    return sorted(required)


def _calculate_automatic_histogram_settings_batch(
    dataframes: list[Any],
    columns: Sequence[str],
) -> dict[str, tuple[int, tuple[float, float]]]:
    """
    Determine automatic settings for many columns at once.

    The key optimization is that every lazy Min/Max/Count/Sum action
    is booked before ROOT.RDF.RunGraphs() is called. Therefore auto
    settings no longer trigger one event loop per requested column.

    Supports scalar columns and ROOT RVec columns and is compatible
    with ImplicitMT.
    """
    unique_columns = list(dict.fromkeys(columns))

    if not unique_columns:
        return {}

    statistics: dict[str, list[dict[str, Any]]] = {
        column: []
        for column in unique_columns
    }

    result_handles = []

    for dataframe_index, dataframe in enumerate(
        dataframes,
        start=1,
    ):
        for column_index, column in enumerate(
            unique_columns,
            start=1,
        ):
            column_type = str(
                dataframe.GetColumnType(column)
            )

            is_rvec = (
                "RVec<" in column_type
                or "ROOT::VecOps::RVec" in column_type
            )

            if is_rvec:
                unique_suffix = (
                    f"{dataframe_index}_{column_index}_"
                    f"{time.time_ns()}"
                )

                temporary_column = (
                    f"__automatic_values_{unique_suffix}"
                )

                working_dataframe = dataframe.Define(
                    temporary_column,
                    f"""
                    ROOT::VecOps::RVec<double> result;
                    result.reserve({column}.size());

                    for (const auto &value : {column}) {{
                        const double converted =
                            static_cast<double>(value);

                        if (std::isfinite(converted)) {{
                            result.emplace_back(converted);
                        }}
                    }}

                    return result;
                    """
                )

                non_empty_dataframe = (
                    working_dataframe.Filter(
                        f"!{temporary_column}.empty()"
                    )
                )

                minimum_column = (
                    f"__automatic_min_{unique_suffix}"
                )
                maximum_column = (
                    f"__automatic_max_{unique_suffix}"
                )
                size_column = (
                    f"__automatic_size_{unique_suffix}"
                )

                statistics_dataframe = (
                    non_empty_dataframe
                    .Define(
                        minimum_column,
                        f"ROOT::VecOps::Min({temporary_column})",
                    )
                    .Define(
                        maximum_column,
                        f"ROOT::VecOps::Max({temporary_column})",
                    )
                    .Define(
                        size_column,
                        f"static_cast<unsigned long long>"
                        f"({temporary_column}.size())",
                    )
                )

                minimum_result = (
                    statistics_dataframe.Min(
                        minimum_column
                    )
                )
                maximum_result = (
                    statistics_dataframe.Max(
                        maximum_column
                    )
                )
                count_result = (
                    statistics_dataframe.Sum(
                        size_column
                    )
                )

            else:
                finite_dataframe = dataframe.Filter(
                    f"std::isfinite("
                    f"static_cast<double>({column}))"
                )

                minimum_result = (
                    finite_dataframe.Min(column)
                )
                maximum_result = (
                    finite_dataframe.Max(column)
                )
                count_result = (
                    finite_dataframe.Count()
                )

            statistics[column].append({
                "type": column_type,
                "minimum": minimum_result,
                "maximum": maximum_result,
                "count": count_result,
            })

            result_handles.extend(
                [
                    minimum_result,
                    maximum_result,
                    count_result,
                ]
            )

    start_time = time.perf_counter()

    ROOT.RDF.RunGraphs(
        result_handles
    )

    elapsed = time.perf_counter() - start_time

    print(
        f"Automatic histogram statistics for "
        f"{len(unique_columns)} column(s) completed "
        f"in {elapsed:.3f} s."
    )

    automatic_settings: dict[
        str,
        tuple[int, tuple[float, float]],
    ] = {}

    for column in unique_columns:
        entry_count = 0
        minima = []
        maxima = []
        column_types = set()

        for item in statistics[column]:
            current_count = int(
                item["count"].GetValue()
            )

            entry_count += current_count
            column_types.add(str(item["type"]))

            # Ignore Min/Max sentinel values from dataframes that
            # contained no finite values for this column.
            if current_count <= 0:
                continue

            minimum = float(
                item["minimum"].GetValue()
            )
            maximum = float(
                item["maximum"].GetValue()
            )

            if np.isfinite(minimum):
                minima.append(minimum)

            if np.isfinite(maximum):
                maxima.append(maximum)

        if entry_count <= 0 or not minima or not maxima:
            raise HistogramError(
                f"Cannot automatically determine histogram "
                f"settings for {column!r}: no finite scalar or "
                f"vector values were found."
            )

        minimum = min(minima)
        maximum = max(maxima)

        if minimum == maximum:
            padding = (
                abs(minimum) * 0.05
                if minimum != 0.0
                else 0.5
            )
        else:
            padding = (
                0.05
                * (maximum - minimum)
            )

        minimum -= padding
        maximum += padding

        bin_count = min(
            200,
            max(
                20,
                int(np.sqrt(entry_count)),
            ),
        )

        automatic_settings[column] = (
            bin_count,
            (minimum, maximum),
        )

        type_text = ", ".join(
            sorted(column_types)
        )

        print(
            f"Automatically determined histogram "
            f"settings for {column}: "
            f"type={type_text}, "
            f"bins={bin_count}, "
            f"range=({minimum:g}, {maximum:g}), "
            f"values={entry_count}"
        )

    return automatic_settings

def _get_required_columns(
    quantity_specs: list[TramQuantitySpec],
) -> set[str]:
    required_columns: set[str] = set()

    for spec in quantity_specs:
        if spec.dimension == 1:
            if spec.column is not None:
                required_columns.add(
                    spec.column
                )

            continue

        if spec.x_column is not None:
            required_columns.add(
                spec.x_column
            )

        if spec.y_column is not None:
            required_columns.add(
                spec.y_column
            )

    return required_columns

def _normalize_dataframes(
    dataframe: Any | list[Any],
) -> list[Any]:
    if isinstance(dataframe, list):
        return dataframe

    return [dataframe]


def _normalize_dataframe_labels(
    dataframe_labels: list[str],
    dataframe_count: int,
) -> list[str]:
    if len(dataframe_labels) != dataframe_count:
        raise HistogramError(
            "Exactly one label must be provided "
            "for each dataframe."
        )

    labels = [
        label.strip()
        for label in dataframe_labels
    ]

    if len(labels) != len(set(labels)):
        raise HistogramError(
            "Dataframe labels must be unique."
        )

    return labels

def _get_tram_quantities(
    quantities: str | list[str],
) -> list[TramQuantitySpec]:
    """
    Parse one or more tram quantities.

    Supported forms
    ---------------
    "Itime"
        One-dimensional histogram.

    "Itime:Iedeposit"
        Two-dimensional histogram using ROOT's Y:X convention.

        x-axis: Itime
        y-axis: Iedeposit
    """
    if isinstance(quantities, str):
        supplied_quantities = [quantities]

    elif isinstance(quantities, list):
        supplied_quantities = quantities

    quantity_specs: list[TramQuantitySpec] = []
    used_expressions: set[str] = set()

    for index, quantity in enumerate(
        supplied_quantities,
        start=1,
    ):
        expression = quantity.strip()
        colon_count = expression.count(":")

        if colon_count == 0:
            spec = TramQuantitySpec(
                expression=expression,
                dimension=1,
                column=expression,
            )

        elif colon_count == 1:
            y_column, x_column = (
                item.strip()
                for item in expression.split(":", 1)
            )

            if not x_column or not y_column:
                raise HistogramError(
                    f"Invalid 2D quantity {expression!r}. "
                    "Use the form 'X_column:Y_column'."
                )

            spec = TramQuantitySpec(
                expression=expression,
                dimension=2,
                x_column=x_column,
                y_column=y_column,
            )

        else:
            raise HistogramError(
                f"Invalid quantity {expression!r}. "
                "Only one ':' is allowed."
            )

        if expression not in used_expressions:
            quantity_specs.append(spec)
            used_expressions.add(expression)

    if not quantity_specs:
        raise HistogramError(
            "At least one tram quantity must be provided."
        )

    return quantity_specs

def _validate_dataframe_columns(
    dataframes: list[Any],
    required_columns: set[str],
    mode_name: str,
) -> None:
    """
    Check that every dataframe contains all required columns.
    """
    for index, current_dataframe in enumerate(
        dataframes,
        start=1,
    ):
        try:
            _validate_required_columns(
                current_dataframe,
                required_columns,
            )
        except Exception as error:
            print(error)
            column_text = ", ".join(
                sorted(required_columns)
            )
            raise HistogramError(
                f"Dataframe {index} does not contain all columns "
                f"required for {mode_name}: {column_text}."
            ) 

def _validate_required_columns(
    dataframe,
    required_columns: set[str],
) -> None:
    available_columns = {
        str(column) for column in dataframe.GetColumnNames()
    }
    missing_columns = required_columns - available_columns

    if missing_columns:
        raise HistogramError(
                "Required branches are missing from the dataframe: "
                + ", ".join(sorted(missing_columns))
            )

def _load_tram_histogram_defaults(
    config_filename: str | Path,
) -> dict[str, Any]:
    """
    Load histogram defaults from a JSON configuration file.

    A missing file is allowed and produces an empty configuration,
    causing the built-in fallback values to be used.
    """
    config_path = Path(config_filename)

    if not config_path.exists():
        return {}

    try:
        with config_path.open(
            "r",
            encoding="utf-8",
        ) as config_file:
            config = json.load(config_file)
    except json.JSONDecodeError as error:
        raise HistogramError(
            f"Invalid JSON in histogram configuration "
            f"{config_path}: {error}"
        ) from error
    except OSError as error:
        raise HistogramError(
            f"Could not read histogram configuration "
            f"{config_path}."
        ) from error

    if not isinstance(config, dict):
        raise HistogramError(
            "The histogram configuration must contain a "
            "JSON object at its top level."
        )

    return config

def _resolve_tram_histogram_settings(
    quantities: list[str],
    bins: int | list[int | None] | None,
    ranges: (
        tuple[float, float]
        | list[float]
        | list[tuple[float, float] | list[float] | None]
        | None
    ),
    config: dict[str, Any],
    emit_log: bool = True,
) -> tuple[
    list[int | None],
    list[tuple[float, float] | None],
]:
    """
    Resolve histogram settings for tram quantities.

    Priority
    --------
    1. Explicit user argument
    2. Exact JSON quantity entry
    3. Matching JSON prefix entry
    4. JSON tram default entry
    5. Built-in fallback

    Built-in fallbacks
    ------------------
    Ordinary tram quantity:
        40 bins, range 0.5 to 40.5

    Quantity beginning with edep_:
        100 bins, range 0 to 1000
    """
    supplied_bins = _get_bins(
        bins,
        len(quantities),
    )

    supplied_ranges = _get_ranges(
        ranges,
        len(quantities),
    )

    tram_config = config.get("tram", {})

    if not isinstance(tram_config, Mapping):
        raise HistogramError(
            "'tram' in the histogram configuration "
            "must be an object."
        )

    default_entry = tram_config.get("default")
    quantity_config = tram_config.get("quantities", {})
    prefix_config = tram_config.get("prefixes", {})

    if not isinstance(quantity_config, Mapping):
        raise HistogramError(
            "'tram.quantities' must be an object."
        )

    if not isinstance(prefix_config, Mapping):
        raise HistogramError(
            "'tram.prefixes' must be an object."
        )

    default_bins, default_range = (
        _parse_histogram_default_entry(
            default_entry,
            context="tram default",
        )
    )

    resolved_bins: list[int | None] = []

    resolved_ranges: list[
        tuple[float, float] | None
    ] = []

    for index, (
        quantity,
        user_bins,
        user_range,
    ) in enumerate(
        zip(
            quantities,
            supplied_bins,
            supplied_ranges,
        ),
        start=1,
    ):
        exact_bins, exact_range = (
            _parse_histogram_default_entry(
                quantity_config.get(quantity),
                context=f"tram quantity {quantity!r}",
            )
        )

        prefix_entry = _find_prefix_configuration(
            quantity,
            prefix_config,
        )

        prefix_bins, prefix_range = (
            _parse_histogram_default_entry(
                prefix_entry,
                context=f"tram prefix for {quantity!r}",
            )
        )

        selected_bins = next(
            (
                value
                for value in (
                    user_bins,
                    exact_bins,
                    prefix_bins,
                    default_bins,
                )
                if value is not None
            ),
            None,
        )

        if (
            selected_bins is not None
            and not _is_positive_integer(selected_bins)
        ):
            raise HistogramError(
                f"The bin count for tram quantity "
                f"{quantity!r} must be a positive integer."
            )
        
        if user_range is not None:
            selected_range = _normalize_histogram_range(
                user_range,
                context=f"tram quantity {quantity!r}",
            )
        else:
            selected_range = next(
                (
                    value
                    for value in (
                        exact_range,
                        prefix_range,
                        default_range,
                    )
                    if value is not None
                ),
                None,
            )

        resolved_bins.append(selected_bins)
        resolved_ranges.append(selected_range)

        if selected_range is None:
            range_text = "automatic"
        else:
            range_text = (
                f"({selected_range[0]:g}, "
                f"{selected_range[1]:g})"
            )

        if emit_log:
            print(
                f"tram histogram {index}: {quantity}, "
                f"bins={selected_bins if selected_bins is not None else 'automatic'}, "
                f"range={range_text}"
            )
    return resolved_bins, resolved_ranges

def _get_bins(
    bins: int | list[int | None] | None,
    quantity_count: int,
) -> list[int | None]:
    if bins is None:
        return [None] * quantity_count

    if isinstance(bins, int) and not isinstance(bins, bool):
        return [bins] * quantity_count

    if isinstance(bins, list):
        if len(bins) != quantity_count:
            raise HistogramError(
                "bins must contain one value for every "
                "tram quantity."
            )

        return list(bins)

    raise HistogramError(
        "bins must be None, a positive integer, or a list "
        "containing integers and None values."
    )

def _get_ranges(
    ranges: (
        tuple[float, float]
        | list[float]
        | list[tuple[float, float] | list[float] | None]
        | None
    ),
    quantity_count: int,
) -> list[tuple[float, float] | list[float] | None]:
    if ranges is None:
        return [None] * quantity_count

    # Permit ranges=(0, 100) or ranges=[0, 100]
    # when only one quantity was requested.
    if quantity_count == 1 and _is_single_range(ranges):
        return [ranges]

    if isinstance(ranges, list):
        if len(ranges) != quantity_count:
            raise HistogramError(
                "ranges must contain one value for every "
                "tram quantity."
            )

        return list(ranges)

    raise HistogramError(
        "ranges must be None, one range for a single "
        "quantity, or a list containing ranges and None."
    )
    

def _is_single_range(
    value: Any,
) -> bool:
    return (
        isinstance(value, (tuple, list))
        and len(value) == 2
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            for item in value
        )
    )

def _find_prefix_configuration(
    quantity: str,
    prefix_config: Mapping[str, Any],
) -> Any:
    """
    Return the most specific matching prefix configuration.

    For example, if both 'edep_' and 'edep_X' exist,
    'edep_X' wins for 'edep_X1L'.
    """
    matching_prefixes = [
        prefix
        for prefix in prefix_config
        if quantity.startswith(prefix)
    ]

    if not matching_prefixes:
        return None

    selected_prefix = max(
        matching_prefixes,
        key=len,
    )

    return prefix_config[selected_prefix]

def _parse_histogram_default_entry(
    entry: Any,
    context: str,
) -> tuple[int | None, tuple[float, float] | None]:
    """
    Validate one histogram-default entry.

    Expected form:

        {
            "bins": 100,
            "range": [0, 1000]
        }
    """
    if entry is None:
        return None, None

    if not isinstance(entry, Mapping):
        raise HistogramError(
            f"The histogram configuration for {context} "
            "must be an object."
        )

    configured_bins = entry.get("bins")
    configured_range = entry.get("range")

    if configured_bins is not None:
        if not _is_positive_integer(configured_bins):
            raise HistogramError(
                f"The configured bin count for {context} "
                "must be a positive integer."
            )

    normalized_range = _normalize_histogram_range(
        configured_range,
        context=f"configured {context}",
    )

    return configured_bins, normalized_range

def _make_tram_histogram_name(
    quantity: str,
    dataset_index: int,
) -> str:
    return (
        f"h_tram_{_make_safe_root_name(quantity)}_"
        f"dataset_{dataset_index}_"
        f"{time.time_ns()}"
    )

def _is_positive_integer(
    value: Any,
) -> bool:
    """
    Return True only for positive integers.

    Booleans are rejected because bool inherits from int.
    """
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0
    )

def _make_safe_root_name(value: str) -> str:
    """
    Create a safe ROOT object name from a detector name.
    """
    safe_name = re.sub(
        pattern=r"[^A-Za-z0-9_]",
        repl="_",
        string=value,
    )

    safe_name = safe_name.strip("_")

    return safe_name or "detector"

def _normalize_histogram_range(
    histogram_range: tuple[float, float] | list[float] | None,
    context: str,
) -> tuple[float, float] | None:
    """
    Validate one optional histogram range.
    """
    if histogram_range is None:
        return None

    if (
        not isinstance(histogram_range, (tuple, list))
        or len(histogram_range) != 2
    ):
        raise HistogramError(
            f"The range for {context} must contain "
            "(minimum, maximum)."
        )

    minimum = float(histogram_range[0])
    maximum = float(histogram_range[1])

    if not np.isfinite(minimum) or not np.isfinite(maximum):
        raise HistogramError(
            f"The range for {context} must contain "
            "finite values."
        )

    if minimum >= maximum:
        raise HistogramError(
            f"The minimum range for {context} must be "
            "smaller than the maximum."
        )

    return minimum, maximum

def _get_tram_2d_bins(
    quantity_specs: list[TramQuantitySpec],
    bins: Any,
) -> dict[str, tuple[int | None, int | None]]:
    """
    Normalize user-provided 2D bin settings.

    The returned tuple follows:

        (x_bins, y_bins)

    For a ROOT expression "Y:X":

        x-axis = X
        y-axis = Y
    """
    two_dimensional_specs = [
        spec
        for spec in quantity_specs
        if spec.dimension == 2
    ]

    if bins is None:
        return {
            spec.expression: (None, None)
            for spec in two_dimensional_specs
        }

    # One 2D expression may receive one pair directly:
    #
    # quantities="Y1L:Z1L"
    # bins=(80, 40)
    if (
        len(two_dimensional_specs) == 1
        and isinstance(bins, tuple)
        and len(bins) == 2
        and all(
            value is None or isinstance(value, int)
            for value in bins
        )
    ):
        return {
            two_dimensional_specs[0].expression: (
                bins[0],
                bins[1],
            )
        }

    if not isinstance(bins, Sequence) or isinstance(
        bins,
        (str, bytes),
    ):
        raise HistogramError(
            "For multiple 2D quantities, bins must be a list "
            "containing one (x_bins, y_bins) pair per quantity."
        )

    bins_list = list(bins)

    if len(bins_list) != len(quantity_specs):
        raise HistogramError(
            "The number of bin settings must match the number "
            f"of quantities. Received {len(bins_list)} settings "
            f"for {len(quantity_specs)} quantities."
        )

    normalized: dict[
        str,
        tuple[int | None, int | None],
    ] = {}

    for spec, setting in zip(
        quantity_specs,
        bins_list,
    ):
        if spec.dimension != 2:
            continue

        if setting is None:
            normalized[spec.expression] = (
                None,
                None,
            )
            continue

        if (
            not isinstance(setting, Sequence)
            or isinstance(setting, (str, bytes))
            or len(setting) != 2
        ):
            raise HistogramError(
                f"Bins for 2D quantity {spec.expression!r} "
                "must be an (x_bins, y_bins) pair."
            )

        x_bins, y_bins = setting

        for axis_name, value in (
            ("x", x_bins),
            ("y", y_bins),
        ):
            if value is not None and (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value <= 0
            ):
                raise HistogramError(
                    f"The {axis_name}-axis bin count for "
                    f"{spec.expression!r} must be a positive "
                    "integer or None."
                )
            
        normalized[spec.expression] = (
            x_bins,
            y_bins,
        )

    return normalized

def _normalize_axis_range(
    value: Any,
    context: str,
) -> tuple[float, float] | None:
    if value is None:
        return None

    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise HistogramError(
            f"{context} must be a (minimum, maximum) pair "
            "or None."
        )

    minimum, maximum = value

    if (
        not isinstance(minimum, (int, float))
        or isinstance(minimum, bool)
        or not isinstance(maximum, (int, float))
        or isinstance(maximum, bool)
    ):
        raise HistogramError(
            f"{context} must contain numeric values."
        )

    minimum = float(minimum)
    maximum = float(maximum)

    if minimum >= maximum:
        raise HistogramError(
            f"{context} must satisfy minimum < maximum."
        )

    return minimum, maximum


def _get_tram_2d_ranges(
    quantity_specs: list[TramQuantitySpec],
    ranges: Any,
) -> dict[
    str,
    tuple[
        tuple[float, float] | None,
        tuple[float, float] | None,
    ],
]:
    """
    Normalize user-provided 2D ranges.

    The returned pair follows:

        (x_range, y_range)
    """
    two_dimensional_specs = [
        spec
        for spec in quantity_specs
        if spec.dimension == 2
    ]

    if ranges is None:
        return {
            spec.expression: (None, None)
            for spec in two_dimensional_specs
        }

    # One 2D expression may receive one pair directly:
    #
    # quantities="Y1L:Z1L"
    # ranges=((0.5, 40.5), (0.5, 40.5))
    if (
        len(two_dimensional_specs) == 1
        and isinstance(ranges, Sequence)
        and not isinstance(ranges, (str, bytes))
        and len(ranges) == 2
    ):
        try:
            x_range = _normalize_axis_range(
                ranges[0],
                context=(
                    f"x-axis range for "
                    f"{two_dimensional_specs[0].expression!r}"
                ),
            )

            y_range = _normalize_axis_range(
                ranges[1],
                context=(
                    f"y-axis range for "
                    f"{two_dimensional_specs[0].expression!r}"
                ),
            )

            return {
                two_dimensional_specs[0].expression: (
                    x_range,
                    y_range,
                )
            }
        except HistogramError:
            # It may instead be a list aligned with all quantities.
            pass

    if not isinstance(ranges, Sequence) or isinstance(
        ranges,
        (str, bytes),
    ):
        raise HistogramError(
            "For multiple 2D quantities, ranges must be a list "
            "containing one (x_range, y_range) pair per quantity."
        )

    ranges_list = list(ranges)

    if len(ranges_list) != len(quantity_specs):
        raise HistogramError(
            "The number of range settings must match the number "
            f"of quantities. Received {len(ranges_list)} settings "
            f"for {len(quantity_specs)} quantities."
        )

    normalized: dict[
        str,
        tuple[
            tuple[float, float] | None,
            tuple[float, float] | None,
        ],
    ] = {}

    for spec, setting in zip(
        quantity_specs,
        ranges_list,
    ):
        if spec.dimension != 2:
            continue

        if setting is None:
            normalized[spec.expression] = (
                None,
                None,
            )
            continue

        if (
            not isinstance(setting, Sequence)
            or isinstance(setting, (str, bytes))
            or len(setting) != 2
        ):
            raise HistogramError(
                f"Ranges for 2D quantity {spec.expression!r} "
                "must be an (x_range, y_range) pair."
            )

        x_range = _normalize_axis_range(
            setting[0],
            context=(
                f"x-axis range for "
                f"{spec.expression!r}"
            ),
        )

        y_range = _normalize_axis_range(
            setting[1],
            context=(
                f"y-axis range for "
                f"{spec.expression!r}"
            ),
        )

        normalized[spec.expression] = (
            x_range,
            y_range,
        )

    return normalized

def _resolve_tram_column_defaults(
    column: str,
    config: dict[str, Any],
) -> tuple[
    int | None,
    tuple[float, float] | None,
]:
    """
    Resolve default bins and range for one tram column.

    Priority
    --------
    1. Exact quantity configuration
    2. Prefix configuration
    3. General tram default
    4. Built-in fallback
    """
    tram_config = config.get("tram", {})

    if not isinstance(tram_config, Mapping):
        raise HistogramError(
            "'tram' in the histogram configuration "
            "must be an object."
        )

    quantity_config = tram_config.get(
        "quantities",
        {},
    )
    prefix_config = tram_config.get(
        "prefixes",
        {},
    )

    if not isinstance(quantity_config, Mapping):
        raise HistogramError(
            "'tram.quantities' must be an object."
        )

    if not isinstance(prefix_config, Mapping):
        raise HistogramError(
            "'tram.prefixes' must be an object."
        )

    default_bins, default_range = (
        _parse_histogram_default_entry(
            tram_config.get("default"),
            context="tram default",
        )
    )

    exact_bins, exact_range = (
        _parse_histogram_default_entry(
            quantity_config.get(column),
            context=f"tram quantity {column!r}",
        )
    )

    prefix_entry = _find_prefix_configuration(
        column,
        prefix_config,
    )

    prefix_bins, prefix_range = (
        _parse_histogram_default_entry(
            prefix_entry,
            context=f"tram prefix for {column!r}",
        )
    )

    selected_bins = next(
        (
            value
            for value in (
                exact_bins,
                prefix_bins,
                default_bins,
            )
            if value is not None
        ),
        None,
    )

    selected_range = next(
        (
            value
            for value in (
                exact_range,
                prefix_range,
                default_range,
            )
            if value is not None
        ),
        None,
    )

    return selected_bins, selected_range

def _make_tram_2d_histogram_name(
    spec: TramQuantitySpec,
    dataset_index: int,
) -> str:
    return (
        f"h2_tram_"
        f"{_make_safe_root_name(spec.y_column or 'y')}_"
        f"{_make_safe_root_name(spec.x_column or 'x')}_"
        f"dataset_{dataset_index}_"
        f"{time.time_ns()}"
    )

def _index_tram_histograms(
    histogram_data_1d: list[dict[str, Any]],
    histogram_data_2d: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Index histograms as:

        histograms[quantity_or_expression][dataframe_label]

    Examples:

        histograms["Y1L"]["dataframe1"]
        histograms["Y1L:Z1L"]["dataframe1"]
    """
    indexed_histograms: dict[
        str,
        dict[str, Any],
    ] = {}

    all_histogram_data = (
        list(histogram_data_1d)
        + list(histogram_data_2d)
    )

    for item in all_histogram_data:
        if item.get("dimension") == 2:
            quantity_key = str(
                item["expression"]
            )
        else:
            quantity_key = str(
                item["quantity"]
            )

        dataframe_label = str(
            item["dataset_label"]
        )

        quantity_histograms = (
            indexed_histograms.setdefault(
                quantity_key,
                {},
            )
        )

        if dataframe_label in quantity_histograms:
            raise HistogramError(
                "Dataframe labels must be unique when indexing "
                "tram histograms. Duplicate label "
                f"{dataframe_label!r} was found for "
                f"{quantity_key!r}."
            )


        quantity_histograms[dataframe_label] = (
            item["histogram"]
        )

    return indexed_histograms