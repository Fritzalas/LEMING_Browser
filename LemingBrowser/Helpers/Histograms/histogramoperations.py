import ROOT
from pathlib import Path
import math
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
from Exceptions.HistogramError import HistogramError
from SaveFiles.savehistograms import save_histograms
from Provenance.provenance import register_provenance

def background_subtraction(
    histograms,
    bkg_min,
    bkg_max,
    saveHistograms: bool,
    outputFileName: str | None
):
    """
    Subtract the average background from ROOT histogram(s) without
    modifying the original histogram(s).

    The background is estimated as the average bin content in the
    interval [bkg_min, bkg_max].

    Parameters
    ----------
    histograms : ROOT.TH1 or list/tuple of ROOT.TH1
        Single histogram or collection of histograms.

    bkg_min : float
        Lower edge of the background region.

    bkg_max : float
        Upper edge of the background region.

    saveHistograms : bool
        If True, save the background-subtracted histograms to a ROOT file.

    outputFileName : str or None
        Name/path of the output ROOT file.
        Required when saveHistograms=True.

    Returns
    -------
    ROOT.TH1 or list of ROOT.TH1
        Background-subtracted clone(s).
    """

    print("Now we are going to apply background subtraction to our histograms")

    # --------------------------------------------------
    # Validate histogram input
    # --------------------------------------------------

    hist_list, is_list = _validate_histograms(histograms)

    # --------------------------------------------------
    # Validate background range
    # --------------------------------------------------

    if not isinstance(bkg_min, (int, float)):
        raise HistogramError(
            f"bkg_min must be a number. "
            f"Got {type(bkg_min).__name__}."
        )

    if not isinstance(bkg_max, (int, float)):
        raise HistogramError(
            f"bkg_max must be a number. "
            f"Got {type(bkg_max).__name__}."
        )

    if not math.isfinite(bkg_min) or not math.isfinite(bkg_max):
        raise HistogramError(
            "Background limits must be finite."
        )

    if bkg_min >= bkg_max:
        raise HistogramError(
            f"bkg_min must be smaller than bkg_max. "
            f"Got [{bkg_min}, {bkg_max}]."
        )

    # --------------------------------------------------
    # Validate saving arguments
    # --------------------------------------------------

    if not isinstance(saveHistograms, bool):
        raise HistogramError(
            f"saveHistograms must be a bool. "
            f"Got {type(saveHistograms).__name__}."
        )

    # --------------------------------------------------
    # Background subtraction
    # --------------------------------------------------

    corrected_histograms = []

    for histogram in hist_list:

        # Clone so the original histogram remains unchanged
        corrected = histogram.Clone(
            histogram.GetName() + "_bkg_subtracted"
        )
        corrected.SetDirectory(0)

        axis = corrected.GetXaxis()
        n_bins = axis.GetNbins()

        if n_bins <= 0:
            raise HistogramError(
                f"Histogram '{histogram.GetName()}' has no bins."
            )

        # Histogram x-axis range
        x_min = axis.GetXmin()
        x_max = axis.GetXmax()

        # Make sure the background range is inside the histogram
        if bkg_min < x_min or bkg_max > x_max:
            raise HistogramError(
                f"Background range [{bkg_min}, {bkg_max}] is outside "
                f"histogram '{histogram.GetName()}' range "
                f"[{x_min}, {x_max}]."
            )

        # --------------------------------------------------
        # Find background bins
        # --------------------------------------------------

        bkg_start = axis.FindBin(bkg_min)
        bkg_end = axis.FindBin(bkg_max)

        n_bkg_bins = bkg_end - bkg_start + 1

        if n_bkg_bins <= 0:
            raise HistogramError(
                f"No valid background bins found for "
                f"'{histogram.GetName()}'."
            )

        # --------------------------------------------------
        # Calculate average background and its uncertainty
        # --------------------------------------------------

        bkg_sum = 0.0
        bkg_variance_sum = 0.0

        for bin_idx in range(bkg_start, bkg_end + 1):

            bin_content = corrected.GetBinContent(bin_idx)
            bin_error = corrected.GetBinError(bin_idx)

            bkg_sum += bin_content
            bkg_variance_sum += bin_error**2

        # Average background
        bkg = bkg_sum / n_bkg_bins

        # Variance/error of the mean background
        bkg_variance = (
            bkg_variance_sum
            / n_bkg_bins**2
        )

        bkg_error = math.sqrt(bkg_variance)

        # --------------------------------------------------
        # Subtract background
        # --------------------------------------------------

        bin_first = axis.FindBin(0.0)
        bin_last = n_bins

        for bin_idx in range(bin_first, bin_last + 1):

            old_content = corrected.GetBinContent(bin_idx)
            old_error = corrected.GetBinError(bin_idx)

            new_content = old_content - bkg

            # --------------------------------------------------
            # Error propagation
            #
            # For bins outside the background interval:
            #
            # Var(N - B) = Var(N) + Var(B)
            #
            # For bins that were used to calculate B:
            #
            # Var(N - B)
            #   = Var(N) + Var(B) - 2 Cov(N, B)
            #
            # Assuming original histogram bins are independent:
            #
            # Cov(N_i, B) = Var(N_i) / n_bkg_bins
            # --------------------------------------------------

            variance = (
                old_error**2
                + bkg_variance
            )

            if bkg_start <= bin_idx <= bkg_end:

                covariance = (
                    old_error**2
                    / n_bkg_bins
                )

                variance -= 2.0 * covariance

            # Protect against very small negative values caused
            # by floating-point precision
            new_error = math.sqrt(
                max(variance, 0.0)
            )

            corrected.SetBinContent(
                bin_idx,
                new_content
            )

            corrected.SetBinError(
                bin_idx,
                new_error
            )

        register_provenance(
            corrected,
            kind="histogram",
            operation="background subtraction",
            parameters={
                "background_min": bkg_min,
                "background_max": bkg_max,
                "background_value": bkg,
                "background_error": bkg_error,
                "background_bins": n_bkg_bins,
            },
            parents=[histogram],
        )

        corrected_histograms.append(corrected)

    # --------------------------------------------------
    # Save histograms if requested
    # --------------------------------------------------

    if saveHistograms:

        histogram_data = [
            {"histogram": hist}
            for hist in corrected_histograms
        ]

        save_histograms(
            output_filename=outputFileName,
            histogram_data=histogram_data
        )

    # --------------------------------------------------
    # Preserve input style
    # --------------------------------------------------

    if not is_list:
        return corrected_histograms[0]

    return corrected_histograms

def lifetime_correction_histo(
    histograms,
    lifetime,
    saveHistograms: bool,
    outputFileName: str | None
):
    """
    Apply lifetime correction to ROOT histogram(s) without modifying
    the original histogram(s).

    Parameters
    ----------
    histograms : ROOT.TH1 or list/tuple of ROOT.TH1
        Single histogram or collection of histograms.

    lifetime : float
        Lifetime constant used in the correction.

    saveHistograms : bool
        If True, save the corrected histograms to a ROOT file.

    outputFileName : str or None
        Name/path of the output ROOT file.
        Required when saveHistograms=True.

    Returns
    -------
    ROOT.TH1 or list of ROOT.TH1
        Corrected clone(s) of the input histogram(s).
    """

    print("Now we are going to apply lifetime correction to our histograms")

    # Validate histogram input
    hist_list, is_list = _validate_histograms(histograms)

    # Validate lifetime
    if not isinstance(lifetime, (int, float)):
        raise HistogramError(
            f"Lifetime must be a number. Got {type(lifetime).__name__}."
        )

    if not math.isfinite(lifetime):
        raise HistogramError(
            "Lifetime must be finite."
        )

    if lifetime <= 0:
        raise HistogramError(
            f"Lifetime must be greater than zero. Got {lifetime}."
        )

    # Validate saving arguments
    if not isinstance(saveHistograms, bool):
        raise HistogramError(
            f"saveHistograms must be a bool. "
            f"Got {type(saveHistograms).__name__}."
        )
    
    corrected_histograms = []

    for histogram in hist_list:

        # Make sure histogram has bins
        n_bins = histogram.GetXaxis().GetNbins()

        if n_bins <= 0:
            raise HistogramError(
                f"Histogram '{histogram.GetName()}' has no bins."
            )

        # Clone so the original histogram is not modified
        corrected = histogram.Clone(
            histogram.GetName() + "_lifetime_corrected"
        )
        corrected.SetDirectory(0)

        bin_first = corrected.GetXaxis().FindBin(0.0)
        bin_last = corrected.GetXaxis().GetNbins()

        for bin_idx in range(bin_first, bin_last + 1):

            bin_center = corrected.GetBinCenter(bin_idx)

            factor = math.exp(
                bin_center / lifetime
            )

            old_bin_content = corrected.GetBinContent(bin_idx)
            old_bin_error = corrected.GetBinError(bin_idx)

            corrected.SetBinContent(
                bin_idx,
                old_bin_content * factor
            )

            corrected.SetBinError(
                bin_idx,
                old_bin_error * factor
            )

        register_provenance(
            corrected,
            kind="histogram",
            operation="lifetime correction",
            parameters={
                "lifetime": lifetime,
                "applied_from_x": 0.0,
            },
            parents=[histogram],
        )

        corrected_histograms.append(corrected)

    # Save corrected histograms if requested
    if saveHistograms:

        histogram_data = [
            {"histogram": hist}
            for hist in corrected_histograms
        ]

        save_histograms(
            output_filename=outputFileName,
            histogram_data=histogram_data
        )

    # Preserve input style
    if not is_list:
        return corrected_histograms[0]

    return corrected_histograms

def Normalize(
    histograms,
    saveHistograms: bool,
    outputFileName: str | None
):

    print("Now we are going to apply normalization to our histograms")

    # Validate input
    hist_list, is_list = _validate_histograms(histograms)

    normalized_histograms = []

    for histogram in hist_list:

        # Clone: original histogram remains unchanged
        normalized = histogram.Clone(
            histogram.GetName() + "_normalized"
        )
        normalized.SetDirectory(0)

        integral = normalized.Integral(
            normalized.FindBin(0),
            normalized.FindBin(8000)
        )

        if integral <= 0:
            print(
                f"WARNING: Histogram '{histogram.GetName()}' "
                f"has integral {integral}. Skipping normalization."
            )
        else:
            normalized.Scale(1.0 / integral)

        was_normalized = integral > 0

        register_provenance(
            normalized,
            kind="histogram",
            operation="normalization",
            parameters={
                "normalization_range": [0, 8000],
                "integral": integral,
                "scale_factor": (
                    1.0 / integral
                    if integral > 0
                    else None
                ),
                "applied": was_normalized,
            },
            parents=[histogram],
        )

        normalized_histograms.append(normalized)

    # Save histograms if requested
    if saveHistograms:
        histogram_data = [
            {"histogram": hist}
            for hist in normalized_histograms
        ]
        save_histograms(
            output_filename=outputFileName,
            histogram_data=histogram_data
        )

    # Preserve input style
    if not is_list:
        return normalized_histograms[0]

    return normalized_histograms

def get_muSR(
    hist1_or_groups,
    hist2,
    saveHistograms: bool,
    outputFileName: str | None
):
    """
    Calculate:

              hist1 - hist2
        A = -----------------
              hist1 + hist2

    using ROOT histogram arithmetic and ROOT bin-error propagation.

    Parameters
    ----------
    hist1_or_groups :
        Either:

        1. A single ROOT histogram. In this case hist2 must also
           be provided.

        or

        2. A list/tuple containing histogram pairs:

           [
               (hist1, hist2),
               (hist3, hist4),
               ...
           ]

    hist2 : ROOT.TH1 or None
        Second histogram when calculating a single pair.

    saveHistograms : bool
        If True, save the resulting muSR histograms to a ROOT file.

    outputFileName : str or None
        Name/path of the output ROOT file.
        Required when saveHistograms=True.

    Returns
    -------
    ROOT.TH1 or list[ROOT.TH1]
        A single muSR histogram for one pair, or a list of muSR
        histograms for multiple pairs.
    """

    print(
        "Now we are going to calculate "
        "(hist1 - hist2) / (hist1 + hist2)"
    )

    # --------------------------------------------------
    # Validate saving arguments
    # --------------------------------------------------

    if not isinstance(saveHistograms, bool):
        raise HistogramError(
            f"saveHistograms must be a bool. "
            f"Got {type(saveHistograms).__name__}."
        )

    # --------------------------------------------------
    # Determine input format
    # --------------------------------------------------

    if hist2 is not None:

        # Single pair
        groups = [(hist1_or_groups, hist2)]
        is_group_list = False

    else:

        # Multiple pairs
        if not isinstance(hist1_or_groups, (list, tuple)):
            raise HistogramError(
                "When hist2 is not provided, the input must be "
                "a list/tuple of histogram pairs."
            )

        if len(hist1_or_groups) == 0:
            raise HistogramError(
                "Histogram group list cannot be empty."
            )

        groups = list(hist1_or_groups)
        is_group_list = True

    # --------------------------------------------------
    # Validate group structure
    # --------------------------------------------------

    for group_idx, group in enumerate(groups):

        if not isinstance(group, (list, tuple)):
            raise HistogramError(
                f"Group {group_idx} must be a list or tuple "
                f"containing exactly two histograms."
            )

        if len(group) != 2:
            raise HistogramError(
                f"Group {group_idx} must contain exactly two "
                f"histograms. Got {len(group)} objects."
            )

    # --------------------------------------------------
    # Calculate muSR asymmetry
    # --------------------------------------------------

    asymmetry_histograms = []

    for group_idx, (hist1, hist2) in enumerate(groups):

        # Validate histogram type, number of bins,
        # axis range and bin edges
        _validate_histogram_pair(hist1, hist2)

        # --------------------------------------------------
        # Create numerator: hist1 - hist2
        # --------------------------------------------------

        numerator = hist1.Clone(
            f"{hist1.GetName()}_{hist2.GetName()}_difference"
        )
        numerator.SetDirectory(0)

        # Make sure ROOT stores bin errors
        if numerator.GetSumw2N() == 0:
            numerator.Sumw2()

        numerator.Add(hist2, -1.0)

        # --------------------------------------------------
        # Create denominator: hist1 + hist2
        # --------------------------------------------------

        denominator = hist1.Clone(
            f"{hist1.GetName()}_{hist2.GetName()}_sum"
        )
        denominator.SetDirectory(0)

        if denominator.GetSumw2N() == 0:
            denominator.Sumw2()

        denominator.Add(hist2, 1.0)

        # --------------------------------------------------
        # Calculate:
        #
        #       hist1 - hist2
        # A = -----------------
        #       hist1 + hist2
        #
        # ROOT propagates the stored bin errors.
        # --------------------------------------------------

        asymmetry = numerator.Clone(
            f"{hist1.GetName()}_{hist2.GetName()}_muSR"
        )
        asymmetry.SetDirectory(0)

        if asymmetry.GetSumw2N() == 0:
            asymmetry.Sumw2()

        asymmetry.Divide(denominator)

        register_provenance(
            asymmetry,
            kind="histogram",
            operation="muSR asymmetry",
            parameters={
                "formula": "(hist1 - hist2) / (hist1 + hist2)",
            },
            parents=[
                hist1,
                hist2,
            ],
        )

        asymmetry_histograms.append(asymmetry)

    # --------------------------------------------------
    # Save all resulting histograms if requested
    # --------------------------------------------------

    if saveHistograms:

        histogram_data = [
            {"histogram": hist}
            for hist in asymmetry_histograms
        ]

        save_histograms(
            output_filename=outputFileName,
            histogram_data=histogram_data
        )

    # --------------------------------------------------
    # Preserve input style
    # --------------------------------------------------

    if not is_group_list:
        return asymmetry_histograms[0]

    return asymmetry_histograms

def add_histograms(
    histograms,
    saveHistograms: bool,
    outputFileName: str | None
):
    """
    Add two or more ROOT histograms.

    result = hist1 + hist2 + hist3 + ...

    The input histograms are not modified.
    """

    print(
        "Now we are going to add our histograms"
    )

    # ---------------------------------------------------------
    # Validate histograms and binning
    # ---------------------------------------------------------

    hist_list = _validate_histogram_group(
        histograms
    )

    if not isinstance(
        saveHistograms,
        bool,
    ):
        raise HistogramError(
            f"saveHistograms must be a bool. "
            f"Got {type(saveHistograms).__name__}."
        )

    # ---------------------------------------------------------
    # Perform addition
    # ---------------------------------------------------------

    result = hist_list[0].Clone(
        hist_list[0].GetName()
        + "_sum"
    )

    result.SetDirectory(
        0
    )

    if result.GetSumw2N() == 0:
        result.Sumw2()

    for histogram in hist_list[1:]:
        result.Add(
            histogram,
            1.0,
        )

    # ---------------------------------------------------------
    # Register provenance FIRST
    # ---------------------------------------------------------

    register_provenance(
        result,
        kind="histogram",
        operation="histogram addition",
        parameters={
            "formula": (
                "hist1 + hist2 + ..."
            ),
            "number_of_histograms": (
                len(hist_list)
            ),
        },
        parents=hist_list,
    )

    # ---------------------------------------------------------
    # Save only AFTER provenance exists
    # ---------------------------------------------------------

    if saveHistograms:
        histogram_data = [
            {
                "histogram": result,
            }
        ]

        save_histograms(
            output_filename=(
                outputFileName
            ),
            histogram_data=(
                histogram_data
            ),
        )

    return result

def subtract_histograms(
    histograms,
    saveHistograms: bool,
    outputFileName: str | None
):
    print(
        "Now we are going to subtract our histograms"
    )

    hist_list = _validate_histogram_group(
        histograms
    )

    if not isinstance(
        saveHistograms,
        bool,
    ):
        raise HistogramError(
            f"saveHistograms must be a bool. "
            f"Got {type(saveHistograms).__name__}."
        )

    result = hist_list[0].Clone(
        hist_list[0].GetName()
        + "_subtraction"
    )

    result.SetDirectory(
        0
    )

    if result.GetSumw2N() == 0:
        result.Sumw2()

    for histogram in hist_list[1:]:
        result.Add(
            histogram,
            -1.0,
        )

    register_provenance(
        result,
        kind="histogram",
        operation="histogram subtraction",
        parameters={
            "formula": (
                "hist1 - hist2 - ..."
            ),
            "number_of_histograms": (
                len(hist_list)
            ),
        },
        parents=hist_list,
    )

    if saveHistograms:
        save_histograms(
            output_filename=(
                outputFileName
            ),
            histogram_data=[
                {
                    "histogram": result,
                }
            ],
        )

    return result

def multiply_histograms(
    histograms,
    saveHistograms: bool,
    outputFileName: str | None
):
    print(
        "Now we are going to multiply our histograms"
    )

    hist_list = _validate_histogram_group(
        histograms
    )

    if not isinstance(
        saveHistograms,
        bool,
    ):
        raise HistogramError(
            f"saveHistograms must be a bool. "
            f"Got {type(saveHistograms).__name__}."
        )

    result = hist_list[0].Clone(
        hist_list[0].GetName()
        + "_product"
    )

    result.SetDirectory(
        0
    )

    if result.GetSumw2N() == 0:
        result.Sumw2()

    for histogram in hist_list[1:]:
        result.Multiply(
            histogram
        )

    register_provenance(
        result,
        kind="histogram",
        operation="histogram multiplication",
        parameters={
            "formula": (
                "hist1 * hist2 * ..."
            ),
            "number_of_histograms": (
                len(hist_list)
            ),
        },
        parents=hist_list,
    )

    if saveHistograms:
        save_histograms(
            output_filename=(
                outputFileName
            ),
            histogram_data=[
                {
                    "histogram": result,
                }
            ],
        )

    return result

def divide_histograms(
    histograms,
    saveHistograms: bool,
    outputFileName: str | None
):
    print(
        "Now we are going to divide our histograms"
    )

    hist_list = _validate_histogram_group(
        histograms
    )

    if not isinstance(
        saveHistograms,
        bool,
    ):
        raise HistogramError(
            f"saveHistograms must be a bool. "
            f"Got {type(saveHistograms).__name__}."
        )

    result = hist_list[0].Clone(
        hist_list[0].GetName()
        + "_division"
    )

    result.SetDirectory(
        0
    )

    if result.GetSumw2N() == 0:
        result.Sumw2()

    for histogram in hist_list[1:]:
        result.Divide(
            histogram
        )

    register_provenance(
        result,
        kind="histogram",
        operation="histogram division",
        parameters={
            "formula": (
                "hist1 / hist2 / ..."
            ),
            "number_of_histograms": (
                len(hist_list)
            ),
        },
        parents=hist_list,
    )

    if saveHistograms:
        save_histograms(
            output_filename=(
                outputFileName
            ),
            histogram_data=[
                {
                    "histogram": result,
                }
            ],
        )

    return result

def _validate_histogram_pair(hist1, hist2):
    """
    Validate that two ROOT histograms have compatible binning.

    Checks:
        - Both objects are ROOT histograms
        - Same number of bins
        - Same x-axis range
        - Same bin edges
    """

    # Validate that both are histograms
    _validate_histograms([hist1, hist2])

    axis1 = hist1.GetXaxis()
    axis2 = hist2.GetXaxis()

    n_bins1 = axis1.GetNbins()
    n_bins2 = axis2.GetNbins()

    # Check number of bins
    if n_bins1 != n_bins2:
        raise HistogramError(
            f"Histograms '{hist1.GetName()}' and '{hist2.GetName()}' "
            f"have different numbers of bins: "
            f"{n_bins1} and {n_bins2}."
        )

    # Check histogram range
    if not math.isclose(
        axis1.GetXmin(),
        axis2.GetXmin(),
        rel_tol=1e-12,
        abs_tol=1e-12
    ):
        raise HistogramError(
            f"Histograms '{hist1.GetName()}' and '{hist2.GetName()}' "
            f"have different lower x-axis limits: "
            f"{axis1.GetXmin()} and {axis2.GetXmin()}."
        )

    if not math.isclose(
        axis1.GetXmax(),
        axis2.GetXmax(),
        rel_tol=1e-12,
        abs_tol=1e-12
    ):
        raise HistogramError(
            f"Histograms '{hist1.GetName()}' and '{hist2.GetName()}' "
            f"have different upper x-axis limits: "
            f"{axis1.GetXmax()} and {axis2.GetXmax()}."
        )

    # Check every bin edge.
    # n_bins + 1 gives us the final upper edge as well.
    for bin_idx in range(1, n_bins1 + 2):

        edge1 = axis1.GetBinLowEdge(bin_idx)
        edge2 = axis2.GetBinLowEdge(bin_idx)

        if not math.isclose(
            edge1,
            edge2,
            rel_tol=1e-12,
            abs_tol=1e-12
        ):
            raise HistogramError(
                f"Histograms '{hist1.GetName()}' and "
                f"'{hist2.GetName()}' have different binning "
                f"at edge {bin_idx}: {edge1} and {edge2}."
            )

    return True

def _validate_histograms(histograms):
    """
    Validate that the input is a ROOT histogram or a list/tuple
    of ROOT histograms.
    """

    if histograms is None:
        raise HistogramError("Input cannot be None.")

    is_list = isinstance(histograms, (list, tuple))

    if is_list:
        if len(histograms) == 0:
            raise HistogramError("Histogram list is empty.")

        hist_list = list(histograms)

    else:
        hist_list = [histograms]

    for i, histogram in enumerate(hist_list):

        if histogram is None:
            raise HistogramError(
                f"Histogram at index {i} is None."
            )

        if not isinstance(histogram, ROOT.TH1):
            raise HistogramError(
                f"Object at index {i} is not a ROOT histogram. "
                f"Got {type(histogram).__name__}."
            )

    return hist_list, is_list

def _validate_histogram_group(histograms):
    """
    Validate a collection of histograms and make sure that all
    histograms have identical binning and x-axis ranges.

    Returns
    -------
    list[ROOT.TH1]
        Validated list of histograms.
    """

    # Validate histogram types and non-empty input
    hist_list, _ = _validate_histograms(histograms)

    if len(hist_list) < 2:
        raise HistogramError(
            "At least two histograms are required."
        )

    # Compare every histogram with the first one
    reference_histogram = hist_list[0]

    for histogram in hist_list[1:]:
        _validate_histogram_pair(
            reference_histogram,
            histogram
        )

    return hist_list