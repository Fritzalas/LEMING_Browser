import matplotlib

# Use an interactive GUI backend.
# This must come BEFORE importing matplotlib.pyplot.
matplotlib.use("QtAgg")

import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter


def plot_sfhe_comparison(
    with_sfhe: list[tuple[float, float]],
    without_sfhe: list[tuple[float, float]],
    title: str,
    xlabel: str,
    ylabel: str,
    save_path: str | None = None,
):
    """
    Plot measurements with and without SFHe
    in an interactive Matplotlib window.
    """

    x_sfhe = [
        point[0]
        for point in with_sfhe
    ]

    y_sfhe = [
        point[1]
        for point in with_sfhe
    ]

    x_no_sfhe = [
        point[0]
        for point in without_sfhe
    ]

    y_no_sfhe = [
        point[1]
        for point in without_sfhe
    ]

    # ---------------------------------------------------------
    # Interactive mode
    # ---------------------------------------------------------

    plt.ion()

    # ---------------------------------------------------------
    # Create figure
    # ---------------------------------------------------------

    fig, ax = plt.subplots(
        figsize=(9, 6)
    )

    # ---------------------------------------------------------
    # With SFHe
    # ---------------------------------------------------------

    ax.plot(
        x_sfhe,
        y_sfhe,
        marker="o",
        markersize=7,
        linewidth=1.8,
        linestyle="-",
        label="With SFHe",
    )

    # ---------------------------------------------------------
    # Without SFHe
    # ---------------------------------------------------------

    line_without, = ax.plot(
        x_no_sfhe,
        y_no_sfhe,
        marker="o",
        markersize=7,
        linewidth=1.6,
        linestyle="--",
        label="Without SFHe",
    )

    line_without.set_markerfacecolor("white")
    line_without.set_markeredgewidth(1.6)

    # ---------------------------------------------------------
    # Labels
    # ---------------------------------------------------------

    ax.set_xlabel(
        xlabel,
        fontsize=13,
    )

    ax.set_ylabel(
        ylabel,
        fontsize=13,
    )

    ax.set_title(
        title,
        fontsize=14,
        pad=14,
    )

    # ---------------------------------------------------------
    # Y axis scale: ×10^-6
    # ---------------------------------------------------------

    formatter = ScalarFormatter(
        useMathText=True
    )

    formatter.set_scientific(True)
    formatter.set_powerlimits((-6, -6))

    ax.yaxis.set_major_formatter(
        formatter
    )

    ax.yaxis.get_offset_text().set_fontsize(
        11
    )

    # ---------------------------------------------------------
    # Grid
    # ---------------------------------------------------------

    ax.grid(
        True,
        which="major",
        linestyle="--",
        linewidth=0.6,
        alpha=0.35,
    )

    ax.minorticks_on()

    ax.grid(
        True,
        which="minor",
        linestyle=":",
        linewidth=0.4,
        alpha=0.15,
    )

    # ---------------------------------------------------------
    # Ticks
    # ---------------------------------------------------------

    ax.tick_params(
        axis="both",
        which="major",
        labelsize=11,
        direction="in",
        top=True,
        right=True,
    )

    ax.tick_params(
        axis="both",
        which="minor",
        direction="in",
        top=True,
        right=True,
    )

    # ---------------------------------------------------------
    # Legend
    # ---------------------------------------------------------

    ax.legend(
        frameon=True,
        fontsize=11,
        loc="best",
    )

    fig.tight_layout()

    # ---------------------------------------------------------
    # Save if requested
    # ---------------------------------------------------------

    if save_path is not None:
        fig.savefig(
            save_path,
            dpi=300,
            bbox_inches="tight",
        )

    # ---------------------------------------------------------
    # Interactive window
    # ---------------------------------------------------------

    plt.show(
        block=False
    )

    fig.canvas.draw()
    fig.canvas.flush_events()

    return fig, ax