import ROOT
import os
import sys


# Getting the name of the directory where this file is present.
current = os.path.dirname(
    os.path.realpath(__file__)
)

# Getting the parent directory.
parent = os.path.dirname(
    current
)

# Adding the parent directory to sys.path.
if parent not in sys.path:
    sys.path.append(
        parent
    )


from Provenance.provenance import register_provenance


def fit_gumbel(
    histograms,
    fit_range,
    gauss_range,
    scale_limits,
    amplitude_limits,
    mu_limits,
    line_color,
):
    """
    Fit one ROOT histogram or a list/tuple of ROOT histograms
    with a Gumbel function.

    A Gaussian fit is performed first to estimate the Gumbel
    location parameter mu.

    Provenance is registered for each fitted histogram and contains:
        - Gumbel fit range
        - Gaussian pre-fit range
        - parameter limits
        - Gaussian-estimated mu
        - Gumbel fitted parameters
        - parameter errors
        - chi-square
        - number of degrees of freedom
        - reduced chi-square
    """

    single_histogram = not isinstance(
        histograms,
        (list, tuple),
    )

    hist_list = (
        [histograms]
        if single_histogram
        else list(histograms)
    )

    xmin, xmax = fit_range

    if gauss_range is None:
        gauss_min, gauss_max = (
            fit_range
        )
    else:
        gauss_min, gauss_max = (
            gauss_range
        )

    fitted_histograms = []

    for i, input_histogram in enumerate(
        hist_list
    ):
        # -----------------------------------------------------
        # Clone histogram so the input remains untouched
        # -----------------------------------------------------

        hist = input_histogram.Clone(
            f"{input_histogram.GetName()}_gumbel_fit"
        )

        # Detach clone from any ROOT TFile/TDirectory.
        # This avoids ownership/lifetime problems.
        hist.SetDirectory(0)

        # Give every TF1 a unique name.
        hist_name = hist.GetName()

        unique_name = (
            f"{hist_name}_{i}"
        )

        # =====================================================
        # 1. Gaussian fit to estimate mu
        # =====================================================

        fit_gauss = ROOT.TF1(
            f"fit_gauss_{unique_name}",
            "gaus",
            gauss_min,
            gauss_max,
        )

        gauss_fit_result = hist.Fit(
            fit_gauss,
            "QSN WL",
            "",
            gauss_min,
            gauss_max,
        )

        mu_estimate = (
            fit_gauss.GetParameter(
                1
            )
        )

        # =====================================================
        # 2. Gumbel fit
        #
        # p0 = beta / scale
        # p1 = mu / location
        # p2 = amplitude
        # =====================================================

        fit_gumbel_function = ROOT.TF1(
            f"fit_gumbel_{unique_name}",
            (
                "[2]/[0] * TMath::Exp("
                "-((x-[1])/[0] "
                "+ TMath::Exp(-(x-[1])/[0]))"
                ")"
            ),
            xmin,
            xmax,
        )

        # -----------------------------------------------------
        # Initial values
        # -----------------------------------------------------

        fit_gumbel_function.SetParameter(
            0,
            1000.0,
        )

        fit_gumbel_function.SetParameter(
            1,
            mu_estimate,
        )

        amplitude_guess = max(
            hist.GetMaximum()
            * 1000.0,
            amplitude_limits[0],
        )

        fit_gumbel_function.SetParameter(
            2,
            amplitude_guess,
        )

        # -----------------------------------------------------
        # Parameter limits
        # -----------------------------------------------------

        fit_gumbel_function.SetParLimits(
            0,
            scale_limits[0],
            scale_limits[1],
        )

        fit_gumbel_function.SetParLimits(
            1,
            mu_limits[0],
            mu_limits[1],
        )

        fit_gumbel_function.SetParLimits(
            2,
            amplitude_limits[0],
            amplitude_limits[1],
        )

        if line_color is not None:
            fit_gumbel_function.SetLineColor(
                line_color
            )

        # =====================================================
        # Gumbel fit
        # =====================================================

        gumbel_fit_result = hist.Fit(
            fit_gumbel_function,
            "SWL",
            "",
            xmin,
            xmax,
        )

        # -----------------------------------------------------
        # Extract fitted values
        # -----------------------------------------------------

        beta = float(
            fit_gumbel_function.GetParameter(
                0
            )
        )

        mu = float(
            fit_gumbel_function.GetParameter(
                1
            )
        )

        amplitude = float(
            fit_gumbel_function.GetParameter(
                2
            )
        )

        beta_error = float(
            fit_gumbel_function.GetParError(
                0
            )
        )

        mu_error = float(
            fit_gumbel_function.GetParError(
                1
            )
        )

        amplitude_error = float(
            fit_gumbel_function.GetParError(
                2
            )
        )

        chi2 = float(
            fit_gumbel_function.GetChisquare()
        )

        ndf = int(
            fit_gumbel_function.GetNDF()
        )

        reduced_chi2 = (
            chi2 / ndf
            if ndf > 0
            else None
        )

        # -----------------------------------------------------
        # Fit statuses
        # -----------------------------------------------------

        gauss_fit_status = int(
            gauss_fit_result
        )

        gumbel_fit_status = int(
            gumbel_fit_result
        )

        # -----------------------------------------------------
        # Keep Python references to TF1 objects
        # -----------------------------------------------------

        hist._gauss_fit = (
            fit_gauss
        )

        hist._gumbel_fit = (
            fit_gumbel_function
        )

        # =====================================================
        # Register provenance
        # =====================================================

        register_provenance(
            hist,
            kind="histogram",
            operation="Gumbel fit",
            parameters={
                # ---------------------------------------------
                # Fit configuration
                # ---------------------------------------------
                "fit_range": [
                    float(xmin),
                    float(xmax),
                ],

                "gaussian_prefit_range": [
                    float(gauss_min),
                    float(gauss_max),
                ],

                "scale_limits": [
                    float(
                        scale_limits[0]
                    ),
                    float(
                        scale_limits[1]
                    ),
                ],

                "mu_limits": [
                    float(
                        mu_limits[0]
                    ),
                    float(
                        mu_limits[1]
                    ),
                ],

                "amplitude_limits": [
                    float(
                        amplitude_limits[0]
                    ),
                    float(
                        amplitude_limits[1]
                    ),
                ],

                "line_color": (
                    int(line_color)
                    if line_color
                    is not None
                    else None
                ),

                # ---------------------------------------------
                # Gaussian pre-fit
                # ---------------------------------------------
                "gaussian_mu_estimate": (
                    float(
                        mu_estimate
                    )
                ),

                "gaussian_fit_status": (
                    gauss_fit_status
                ),

                # ---------------------------------------------
                # Gumbel fit result
                # ---------------------------------------------
                "beta": beta,
                "beta_error": (
                    beta_error
                ),

                "mu": mu,
                "mu_error": (
                    mu_error
                ),

                "amplitude": (
                    amplitude
                ),

                "amplitude_error": (
                    amplitude_error
                ),

                "chi2": chi2,
                "ndf": ndf,

                "reduced_chi2": (
                    reduced_chi2
                ),

                "fit_status": (
                    gumbel_fit_status
                ),

                # ---------------------------------------------
                # Formula
                # ---------------------------------------------
                "formula": (
                    "[2]/[0] * exp("
                    "-((x-[1])/[0] "
                    "+ exp(-(x-[1])/[0])))"
                ),
            },
            parents=[
                input_histogram,
            ],
        )

        fitted_histograms.append(
            hist
        )

    if single_histogram:
        return (
            fitted_histograms[0]
        )

    return fitted_histograms