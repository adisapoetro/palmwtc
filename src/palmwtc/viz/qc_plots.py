"""QC flag visualisation for chamber sensor streams.

Static matplotlib plots that turn the QC output of
:mod:`palmwtc.qc.rules` and :mod:`palmwtc.qc.processor` into
human-readable diagnostics:

- :func:`visualize_qc_flags` -- multi-panel scatter coloured by flag value,
  with per-method breakdown panels and a summary row.
- :func:`plot_qc_comparison` -- 2x2 horizontal-bar + stacked-bar comparison
  of flag percentages across multiple variables.
- :func:`plot_qc_summary_heatmap` -- heatmap of flag percentages, one row per
  variable, three columns (Flag 0 / 1 / 2).
- :func:`filter_plot` -- two-chamber overlay for one variable with hard/soft
  threshold lines drawn on the axes.
- :func:`plot_soil_var` -- multi-depth soil sensor profile drawn on a single
  axis (depths 15, 48, 80, 200, 350 cm).
- :func:`plot_high_quality_timeseries` -- line plot of Flag-0 data only.
- :func:`plot_drift_and_hq_timeseries` -- two-panel figure: drift score (top)
  and Flag-0 timeseries (bottom), sharing the x-axis.
- :func:`plot_baseline_drift` -- daily minimum/mean overlay with an expected
  baseline value and tolerance band.
- :func:`plot_breakpoints_analysis` -- two-figure set: (1) timeseries with
  breakpoint lines and segment means; (2) breakpoint table.
- :func:`visualize_breakpoints` -- three-panel overview: timeseries with
  kept/ignored breakpoint lines, segment means, and confidence-score bars.
- :func:`visualize_missing_data` -- two-panel figure showing the raw
  timeseries (top) and gap-duration bars over time (bottom).
- :func:`visualize_drift` -- deprecated stub; prints a notice and returns.

Flag value semantics used throughout this module:

- ``0`` = Good (green).
- ``1`` = Suspect / soft warning (orange).
- ``2`` = Bad / hard fail (red).

All plots use :func:`matplotlib.pyplot` defaults. No custom style is applied
inside this module; call :func:`palmwtc.viz.set_style` before plotting if you
want the package-wide appearance.

Notes
-----
Visualization functions are deterministic and do not require random seeds.
"""

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def visualize_qc_flags(
    df: pd.DataFrame,
    var_name: str,
    qc_results: dict,
    config: dict | None = None,
    figsize: tuple[float, float] = (15, 20),
) -> "matplotlib.figure.Figure | None":
    """Multi-panel scatter plot of QC flags with per-method breakdown.

    Produces a figure whose row count adapts to how many QC methods fired:

    - **Row 1** (combined): scatter plot of ``var_name`` coloured by the
      combined ``{var_name}_qc_flag`` column.  Green = Flag 0, orange =
      Flag 1, red x = Flag 2.  Hard/soft bound lines added when ``config``
      is supplied.
    - **Rows 2..N** (one per active method): the raw timeseries in grey
      with flagged points coloured orange (Suspect) or red-x (Bad).
      Active methods checked: Physical Bounds, Persistence, Rate of Change,
      IQR Outliers.
    - **Last row** (summary): left panel = bar chart of flag counts (Good /
      Suspect / Bad); right panel = horizontal bar chart of flag counts by
      method (Bounds / IQR / RoC / Persist).

    Parameters
    ----------
    df : pd.DataFrame
        QC-flagged DataFrame.  Must contain:

        ``{var_name}`` : numeric
            Raw sensor values.
        ``{var_name}_qc_flag`` : int in {0, 1, 2}
            Combined QC flag column.  May be absent if
            ``qc_results["final_flags"]`` is provided instead.
    var_name : str
        Name of the sensor variable column to plot.
    qc_results : dict
        Per-variable QC result dict from
        :func:`palmwtc.qc.process_variable_qc`.  Expected keys:

        ``"final_flags"`` : pd.Series
            Combined flag series (used as fallback if the flag column is
            absent from ``df``).
        ``"bounds_flags"`` : pd.Series or None
            Flags from the Physical Bounds rule.
        ``"persistence_flags"`` : pd.Series or None
            Flags from the Persistence rule.
        ``"roc_flags"`` : pd.Series or None
            Flags from the Rate-of-Change rule.
        ``"iqr_flags"`` : pd.Series or None
            Flags from the IQR Outlier rule.
        ``"summary"`` : dict
            Keys ``"flag_0_count"``, ``"flag_1_count"``, ``"flag_2_count"``.
    config : dict, optional
        Variable configuration used for axis labels and threshold lines.
        Expected keys (all optional):

        ``"label"`` : str
            Y-axis label.
        ``"soft"`` : tuple of (float, float)
            (min, max) soft bounds drawn as orange dashed lines.
        ``"hard"`` : tuple of (float, float)
            (min, max) hard bounds drawn as red dashed lines.
    figsize : tuple of (float, float), optional
        Figure width and height in inches.  Height is overridden upward
        when many method panels are present (4 rows per extra method).

    Returns
    -------
    matplotlib.figure.Figure or None
        The figure, or ``None`` if ``var_name`` is not found in ``df``.

    Notes
    -----
    Flag values:

    - ``0`` = Good (green scatter, small points).
    - ``1`` = Suspect (orange scatter, medium points).
    - ``2`` = Bad (red x scatter, slightly larger points).

    The summary row reads counts from ``qc_results["summary"]``, which
    reflects the full (unfiltered) dataset.

    Examples
    --------
    >>> from palmwtc.viz.qc_plots import visualize_qc_flags
    >>> fig = visualize_qc_flags(df, "CO2_Avg", qc_results["CO2_Avg"])  # doctest: +SKIP

    See Also
    --------
    palmwtc.qc.process_variable_qc : Produces the ``qc_results`` dict
        consumed here.
    plot_qc_comparison : Compare flag percentages across many variables.
    plot_qc_summary_heatmap : Heatmap view across all variables.
    """
    # ---------------------------------------------------------
    # 1. SPECIAL DATA FILTERING (User Requested)
    # ---------------------------------------------------------
    plot_df = df.copy()

    flag_col = f"{var_name}_qc_flag"
    if flag_col not in plot_df.columns and "final_flags" in qc_results:
        # Re-attach if missing (though usually df has it)
        plot_df[flag_col] = qc_results["final_flags"]

    if var_name not in plot_df.columns:
        print(f"Error: Variable {var_name} not found in dataframe")
        return None

    # ---------------------------------------------------------
    # 2. Identify Active QC Methods
    # ---------------------------------------------------------
    # Map friendly names to qc_results keys
    methods = {
        "Physical Bounds": "bounds_flags",
        "Persistence": "persistence_flags",
        "Rate of Change": "roc_flags",
        "IQR Outliers": "iqr_flags",
    }

    # Filter to methods that actually have results and raised flags
    active_methods = []
    for label, key in methods.items():
        if key in qc_results and qc_results[key] is not None:
            # Check if any flags > 0 exist for this method (intersected with plot_df index)
            flags = qc_results[key]
            # Align flags with plot_df (in case of filtering)
            flags = flags.reindex(plot_df.index).fillna(0)

            if (flags > 0).sum() > 0:
                active_methods.append((label, key, flags))
            elif key == "bounds_flags":  # Always show bounds if relevant?
                # Even if 0 flags, bounds are useful context.
                active_methods.append((label, key, flags))

    # Remove duplicates or order? Ordered by dict definition.

    # Total panels = 1 (Combined) + len(active_methods) + 1 (Summary Row)
    n_method_panels = len(active_methods)
    total_rows = 1 + n_method_panels + 1

    # Adjust figsize based on rows
    if total_rows > 5:
        figsize = (figsize[0], 4 * total_rows)

    fig = plt.figure(figsize=figsize)
    gs = fig.add_gridspec(total_rows, 2, height_ratios=[1.5] + [1] * n_method_panels + [0.8])

    # Define common styles (legacy locals retained for parity with upstream API)
    _colors = {0: "green", 1: "orange", 2: "red"}
    _labels = {0: "Good", 1: "Suspect", 2: "Bad"}

    # ---------------------------------------------------------
    # Panel 1: Overall Combined Flags
    # ---------------------------------------------------------
    ax_main = fig.add_subplot(gs[0, :])

    # Plot Good (0) first (bottom layer)
    mask0 = plot_df[flag_col] == 0
    if mask0.any():
        ax_main.scatter(
            plot_df.index[mask0],
            plot_df.loc[mask0, var_name],
            c="green",
            alpha=0.5,
            s=2,
            label="Good (Flag 0)",
            rasterized=True,
        )

    # Plot Suspect (1)
    mask1 = plot_df[flag_col] == 1
    if mask1.any():
        ax_main.scatter(
            plot_df.index[mask1],
            plot_df.loc[mask1, var_name],
            c="orange",
            alpha=0.8,
            s=15,
            label="Suspect (Flag 1)",
            rasterized=True,
        )

    # Plot Bad (2) - Top layer
    mask2 = plot_df[flag_col] == 2
    if mask2.any():
        ax_main.scatter(
            plot_df.index[mask2],
            plot_df.loc[mask2, var_name],
            c="red",
            alpha=0.9,
            s=20,
            marker="x",
            label="Bad (Flag 2)",
            rasterized=True,
        )

    # Add bounds if config exists
    if config:
        if "soft" in config:
            smin, smax = config["soft"]
            ax_main.axhline(smin, c="orange", ls="--", alpha=0.5, label="Soft Bound")
            ax_main.axhline(smax, c="orange", ls="--", alpha=0.5)
        if "hard" in config:
            hmin, hmax = config["hard"]
            ax_main.axhline(hmin, c="red", ls="--", alpha=0.5, label="Hard Bound")
            ax_main.axhline(hmax, c="red", ls="--", alpha=0.5)

    ax_main.set_title(f"Overall QC Status: {var_name}", fontsize=14, fontweight="bold")
    ax_main.set_ylabel(config.get("label", var_name) if config else var_name)
    ax_main.legend(loc="upper right", ncol=3)
    ax_main.grid(True, alpha=0.3)

    # Set nice Y-limits based on DATA only (ignoring bounds)
    y_vals = plot_df[var_name].dropna()
    y_min, y_max = None, None

    if not y_vals.empty:
        # Calculate data range with padding
        d_min, d_max = y_vals.min(), y_vals.max()
        if d_min == d_max:
            padding = abs(d_min) * 0.1 if d_min != 0 else 1.0
        else:
            padding = (d_max - d_min) * 0.1  # 10% padding

        y_min = d_min - padding
        y_max = d_max + padding

        ax_main.set_ylim(y_min, y_max)

    # ---------------------------------------------------------
    # Panels 2...N: Individual Method Flags
    # ---------------------------------------------------------

    # Determine distinct colors for methods to aid visual separation
    method_colors = ["#1f77b4", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]

    for i, (label, _key, flags) in enumerate(active_methods):
        ax = fig.add_subplot(gs[i + 1, :], sharex=ax_main)

        # Plot underlying data in faint grey
        ax.plot(plot_df.index, plot_df[var_name], color="gray", alpha=0.3, linewidth=0.5, zorder=0)

        # Plot flagged points
        # Flags can be 1 or 2.
        # Find points where this specific method raised a flag > 0
        mask_method = flags > 0

        if mask_method.any():
            subset = plot_df.loc[mask_method]
            subset_flags = flags.loc[mask_method]

            # Scatter points

            # Suspect (1)
            suspects = subset[subset_flags == 1]
            if not suspects.empty:
                ax.scatter(
                    suspects.index,
                    suspects[var_name],
                    c="orange",
                    s=10,
                    label=f"{label} (Suspect)",
                    zorder=2,
                )

            # Bad (2)
            bads = subset[subset_flags == 2]
            if not bads.empty:
                ax.scatter(
                    bads.index,
                    bads[var_name],
                    c="red",
                    s=15,
                    marker="x",
                    label=f"{label} (Bad)",
                    zorder=3,
                )

        ax.set_ylabel(var_name)
        ax.set_title(f"Method: {label}", fontsize=12, loc="left")
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

        # Add specific visual aids for methods
        if label == "Physical Bounds" and config:
            # Show bounds
            if "soft" in config:
                ax.axhline(config["soft"][0], c="orange", ls="--", alpha=0.5)
                ax.axhline(config["soft"][1], c="orange", ls="--", alpha=0.5)
            if "hard" in config:
                ax.axhline(config["hard"][0], c="red", ls="--", alpha=0.5)
                ax.axhline(config["hard"][1], c="red", ls="--", alpha=0.5)

        # Enforce same limits as main plot if calculated
        if y_min is not None and y_max is not None:
            ax.set_ylim(y_min, y_max)

    # ---------------------------------------------------------
    # Last Panel: Summary Stats (Side by Side)
    # ---------------------------------------------------------
    # Use the bottom row (gs[last, :]) but split it into two sub-axes?
    # Actually gs works by cell. We can just take gs[last, 0] and gs[last, 1]

    last_row_idx = total_rows - 1

    # Distribution Chart
    ax_dist = fig.add_subplot(gs[last_row_idx, 0])
    summary = qc_results["summary"]
    flgs = [0, 1, 2]
    cnts = [summary["flag_0_count"], summary["flag_1_count"], summary["flag_2_count"]]
    # Re-calculate counts if we filtered plot_df?
    # qc_results['summary'] assumes full DF.
    # Whatever, plotting the official summary is safer.

    bars = ax_dist.bar(flgs, cnts, color=["green", "orange", "red"], alpha=0.7, edgecolor="black")
    ax_dist.set_xticks(flgs)
    ax_dist.set_xticklabels(["Good", "Suspect", "Bad"])
    ax_dist.set_title("Overall Flag Distribution")
    for bar, c in zip(bars, cnts, strict=False):
        if c > 0:
            ax_dist.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{c:,}",
                ha="center",
                va="bottom",
            )

    # Method Breakdown Chart
    ax_break = fig.add_subplot(gs[last_row_idx, 1])

    # Get counts for each method from original qc_results (pre-filter)
    # Because we want to show why things were flagged even if we filtered them from view?
    # Actually, usually prefer consistent view. But let's stick to qc_results counts.

    m_labels = []
    m_counts = []

    # Helper to count flags > 0 safely
    def count_flags(k):
        if k in qc_results and qc_results[k] is not None:
            return (qc_results[k] > 0).sum()
        return 0

    breakdown_order = [
        ("Bounds", "bounds_flags"),
        ("IQR", "iqr_flags"),
        ("RoC", "roc_flags"),
        ("Persist", "persistence_flags"),
    ]

    for nice, k in breakdown_order:
        m_labels.append(nice)
        m_counts.append(count_flags(k))

    y_pos = np.arange(len(m_labels))
    ax_break.barh(
        y_pos, m_counts, color=method_colors[: len(m_labels)], alpha=0.7, edgecolor="black"
    )
    ax_break.set_yticks(y_pos)
    ax_break.set_yticklabels(m_labels)
    ax_break.set_title("Flag Count by Method")
    ax_break.set_xlabel("Count")

    for i, v in enumerate(m_counts):
        if v > 0:
            ax_break.text(v, i, f" {v:,}", va="center")

    plt.tight_layout()
    return fig


def plot_qc_comparison(
    df: pd.DataFrame,
    var_names: list[str],
    qc_results: dict,
    figsize: tuple[float, float] | None = None,
) -> "matplotlib.figure.Figure":
    """2x2 panel comparison of QC flag percentages across multiple variables.

    Creates a 2x2 figure with horizontal bar charts:

    - **Panel 1 (top-left)**: Flag 0 (Good) percentage per variable.
      A vertical red dashed line marks 50 %.
    - **Panel 2 (top-right)**: Flag 1 (Suspect) percentage per variable.
    - **Panel 3 (bottom-left)**: Flag 2 (Bad) percentage per variable.
      A vertical orange dashed line marks 10 % as a reference threshold.
    - **Panel 4 (bottom-right)**: Stacked horizontal bar chart showing
      Good + Suspect + Bad as proportions of 100 % for each variable.

    Variables appear in reversed order on the y-axis so the first variable
    in ``var_names`` is at the top of each panel.

    Parameters
    ----------
    df : pd.DataFrame
        QC-flagged DataFrame.  Not directly read inside this function;
        passed for API consistency with other QC plot functions.
    var_names : list of str
        Variable names to include.  Only variables that exist in
        ``qc_results`` are shown.
    qc_results : dict
        Mapping ``{var_name: result_dict}``.  Each ``result_dict`` must
        contain either:

        - A nested ``"summary"`` dict with keys ``"flag_0_percent"``,
          ``"flag_1_percent"``, ``"flag_2_percent"``  (V1 structure), or
        - Those same keys at the top level (V2 flat structure).
    figsize : tuple of (float, float), optional
        Figure width and height in inches.  Default: ``(18, height)``
        where height scales with the number of variables
        (minimum 12 inches).

    Returns
    -------
    matplotlib.figure.Figure
        The 2x2 figure.

    Notes
    -----
    All four panels share the same y-axis variable list.  The x-axis is
    fixed to 0-105 % in all panels so the eye can compare across panels
    without re-scaling.

    Examples
    --------
    >>> from palmwtc.viz.qc_plots import plot_qc_comparison
    >>> fig = plot_qc_comparison(df, ["CO2_Avg", "H2O_Avg"], qc_results)  # doctest: +SKIP

    See Also
    --------
    visualize_qc_flags : Single-variable multi-method breakdown.
    plot_qc_summary_heatmap : Heatmap view of the same percentages.
    """
    # Dynamic size calculation if not provided
    if figsize is None:
        # Estimate height: ~0.4 inches per variable per panel row (2 rows)
        # Minimum 12 inches, max reasonably large
        panel_height = max(6, len(var_names) * 0.4)
        total_height = panel_height * 2
        figsize = (18, total_height)

    fig, axes = plt.subplots(2, 2, figsize=figsize)
    axes = axes.flatten()

    # Prepare data
    # Prepare data
    summaries = {}
    for var in var_names:
        if var in qc_results:
            res = qc_results[var]
            # Handle both V1 (nested 'summary') and V2 (flat summary) structures
            if "summary" in res:
                summaries[var] = res["summary"]
            else:
                summaries[var] = res

    var_list = list(summaries.keys())
    # Sort reversed so top variable is at the top of the plot
    var_list_rev = var_list[::-1]

    flag0_pcts = [summaries[v]["flag_0_percent"] for v in var_list_rev]
    flag1_pcts = [summaries[v]["flag_1_percent"] for v in var_list_rev]
    flag2_pcts = [summaries[v]["flag_2_percent"] for v in var_list_rev]

    y_pos = np.arange(len(var_list_rev))

    # Common layout settings
    def setup_ax(ax, title, xlabel="Percentage (%)"):
        ax.set_yticks(y_pos)
        ax.set_yticklabels(var_list_rev)
        ax.set_xlabel(xlabel, fontsize=11)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.grid(True, alpha=0.3, axis="x")
        # Ensure x-axis is 0-100 or slightly more
        ax.set_xlim(0, 105)

    # Panel 1: Flag 0 (Good) percentages
    ax = axes[0]
    ax.barh(y_pos, flag0_pcts, color="green", alpha=0.7, edgecolor="black")
    setup_ax(ax, "Flag 0 (Good Quality)")
    ax.axvline(x=50, color="red", linestyle="--", alpha=0.5, linewidth=1)

    # Panel 2: Flag 1 (Suspect) percentages
    ax = axes[1]
    ax.barh(y_pos, flag1_pcts, color="orange", alpha=0.7, edgecolor="black")
    setup_ax(ax, "Flag 1 (Suspect)")

    # Panel 3: Flag 2 (Bad) percentages
    ax = axes[2]
    ax.barh(y_pos, flag2_pcts, color="red", alpha=0.7, edgecolor="black")
    setup_ax(ax, "Flag 2 (Bad)")
    ax.axvline(x=10, color="orange", linestyle="--", alpha=0.5, linewidth=1, label="10% threshold")
    ax.legend()

    # Panel 4: Stacked bar chart
    ax = axes[3]
    ax.barh(y_pos, flag0_pcts, color="green", alpha=0.7, label="Good (0)", edgecolor="black")
    ax.barh(
        y_pos,
        flag1_pcts,
        left=flag0_pcts,
        color="orange",
        alpha=0.7,
        label="Suspect (1)",
        edgecolor="black",
    )
    left_vals = [f0 + f1 for f0, f1 in zip(flag0_pcts, flag1_pcts, strict=False)]
    ax.barh(
        y_pos,
        flag2_pcts,
        left=left_vals,
        color="red",
        alpha=0.7,
        label="Bad (2)",
        edgecolor="black",
    )

    setup_ax(ax, "Stacked Flag Distribution")
    ax.legend(loc="upper right", bbox_to_anchor=(1, 1.1))  # Adjust legend to not cover data

    plt.tight_layout()
    return fig


def plot_qc_summary_heatmap(
    qc_results: dict,
    figsize: tuple[float, float] = (14, 10),
) -> "matplotlib.figure.Figure":
    """Heatmap of QC pass/suspect/fail percentages for all variables.

    Rows = variables (in the order of ``qc_results`` keys).
    Columns = Flag 0 (Good), Flag 1 (Suspect), Flag 2 (Bad).
    Cell colour uses the ``RdYlGn`` colormap (green = high percentage,
    red = low percentage), anchored at 0-100 %.
    Each cell is annotated with the numeric value ``"XX.X%"``.
    A colourbar on the right shows the percentage scale.

    Parameters
    ----------
    qc_results : dict
        Mapping ``{var_name: result_dict}``.  Each ``result_dict`` must
        contain either a nested ``"summary"`` sub-dict or the summary keys
        at the top level.  Required keys inside the summary:

        ``"flag_0_percent"`` : float
            Percentage of timestamps with Flag 0 (Good).
        ``"flag_1_percent"`` : float
            Percentage of timestamps with Flag 1 (Suspect).
        ``"flag_2_percent"`` : float
            Percentage of timestamps with Flag 2 (Bad).
    figsize : tuple of (float, float), optional
        Figure width and height in inches.

    Returns
    -------
    matplotlib.figure.Figure
        The heatmap figure.

    Notes
    -----
    The three percentage columns for a given variable should sum to
    approximately 100 %.  Small deviations are possible due to rounding.

    Examples
    --------
    >>> from palmwtc.viz.qc_plots import plot_qc_summary_heatmap
    >>> fig = plot_qc_summary_heatmap(qc_results)  # doctest: +SKIP

    See Also
    --------
    plot_qc_comparison : Same percentages as horizontal bar charts.
    visualize_qc_flags : Per-variable, per-method scatter breakdown.
    """
    # Prepare data matrix
    var_names = list(qc_results.keys())

    data = []
    for var in var_names:
        res = qc_results[var]
        # Handle both V1 (nested 'summary') and V2 (flat summary) structures
        summary = res.get("summary", res)

        data.append(
            [summary["flag_0_percent"], summary["flag_1_percent"], summary["flag_2_percent"]]
        )

    data_array = np.array(data)

    # Create heatmap
    fig, ax = plt.subplots(figsize=figsize)

    im = ax.imshow(data_array, cmap="RdYlGn", aspect="auto", vmin=0, vmax=100)

    # Set ticks and labels
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["Flag 0\\n(Good)", "Flag 1\\n(Suspect)", "Flag 2\\n(Bad)"], fontsize=11)
    ax.set_yticks(np.arange(len(var_names)))
    ax.set_yticklabels(var_names, fontsize=9)

    # Add colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Percentage (%)", rotation=270, labelpad=20, fontsize=11)

    # Add text annotations
    for i in range(len(var_names)):
        for j in range(3):
            ax.text(
                j,
                i,
                f"{data_array[i, j]:.1f}%",
                ha="center",
                va="center",
                color="black",
                fontsize=8,
                fontweight="bold",
            )

    ax.set_title("Quality Control Summary - All Variables", fontsize=14, fontweight="bold", pad=20)

    plt.tight_layout()
    return fig


def filter_plot(
    ax: "matplotlib.axes.Axes",
    df_: pd.DataFrame,
    col_c1: str,
    col_c2: str,
    var_key: str,
    var_config: dict,
    use_physical_limits: bool = True,
    ylim_padding_frac: float = 0.06,
) -> None:
    """Draw a two-chamber overlay for one variable onto an existing axis.

    Plots the Chamber 1 series (blue) and Chamber 2 series (red) for the
    variable ``var_key``.  When ``use_physical_limits=True``, points outside
    the hard bounds are removed before plotting, and hard/soft threshold
    lines are drawn as dashed/dotted horizontal lines.

    The y-axis is locked to the range of the *plotted* data plus
    ``ylim_padding_frac`` padding on each side, so threshold lines never
    expand the visible range beyond the data.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Axes to draw on.  The function modifies ``ax`` in place and
        returns ``None``.
    df_ : pd.DataFrame
        DataFrame with a ``TIMESTAMP`` column and the sensor columns.
        Must contain:

        ``TIMESTAMP`` : pd.Timestamp
            Datetime column used for the x-axis.
        ``{col_c1}`` : numeric, optional
            Chamber 1 values.
        ``{col_c2}`` : numeric, optional
            Chamber 2 values.
    col_c1 : str
        Column name for Chamber 1 data in ``df_``.
    col_c2 : str
        Column name for Chamber 2 data in ``df_``.
    var_key : str
        Key used to look up the variable's configuration inside
        ``var_config``.
    var_config : dict
        Mapping ``{var_key: config_dict}``.  The ``config_dict`` may
        contain:

        ``"hard"`` : tuple of (float, float)
            (min, max) hard bounds.  Points outside are removed when
            ``use_physical_limits=True``.  Drawn as red dashed lines.
        ``"soft"`` : tuple of (float, float)
            (min, max) soft bounds.  Drawn as orange dotted lines.
        ``"label"`` : str
            Y-axis label.
        ``"title"`` : str
            Axis title.
    use_physical_limits : bool, optional
        If ``True``, remove values outside hard bounds before plotting and
        draw threshold lines.  Default: ``True``.
    ylim_padding_frac : float, optional
        Fraction of data range added as padding above and below the
        y-axis limits.  Default: 0.06.

    Returns
    -------
    None
        The axis is modified in place.

    Notes
    -----
    If ``var_key`` is not found in ``var_config``, the function sets a
    plain title and grid, then returns without plotting.

    If neither chamber column contains any valid (non-NaN, in-bounds) data,
    the function likewise returns after setting the title.

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> from palmwtc.viz.qc_plots import filter_plot
    >>> fig, ax = plt.subplots()
    >>> filter_plot(ax, df, "C1_CO2", "C2_CO2", "CO2", var_config)  # doctest: +SKIP

    See Also
    --------
    plot_soil_var : Similar helper for multi-depth soil variables.
    """
    if var_key not in var_config:
        ax.set_title(var_key)
        ax.grid(True, alpha=0.3)
        return

    config = var_config[var_key]
    min_h, max_h = config.get("hard", (-np.inf, np.inf))
    min_s, max_s = config.get("soft", (-np.inf, np.inf))
    label_y = config.get("label", var_key)
    title = config.get("title", var_key)

    use_limits = bool(use_physical_limits)

    # Collect plotted series so y-lims reflect plotted data only (not thresholds)
    y_series = []

    # Chamber 1
    if col_c1 in df_.columns:
        data1 = df_[["TIMESTAMP", col_c1]].dropna()
        if use_limits:
            data1 = data1[(data1[col_c1] >= min_h) & (data1[col_c1] <= max_h)]
        if not data1.empty:
            ax.plot(
                data1["TIMESTAMP"],
                data1[col_c1],
                label="Chamber 1",
                color="#1f77b4",
                alpha=0.8,
                linewidth=1.0,
            )
            y_series.append(data1[col_c1].to_numpy())

    # Chamber 2
    if col_c2 in df_.columns:
        data2 = df_[["TIMESTAMP", col_c2]].dropna()
        if use_limits:
            data2 = data2[(data2[col_c2] >= min_h) & (data2[col_c2] <= max_h)]
        if not data2.empty:
            ax.plot(
                data2["TIMESTAMP"],
                data2[col_c2],
                label="Chamber 2",
                color="#d62728",
                alpha=0.8,
                linewidth=1.0,
            )
            y_series.append(data2[col_c2].to_numpy())

    ax.set_ylabel(label_y)

    # If nothing plotted, exit cleanly
    if not y_series:
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        return

    # ----- Y-limits based on ALL plotted data (no clipping) -----
    y_all = np.concatenate(y_series)
    y_all = y_all[np.isfinite(y_all)]

    if y_all.size == 0:
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        return

    y_lo = np.nanmin(y_all)
    y_hi = np.nanmax(y_all)

    # Padding while preserving full data visibility
    if np.isclose(y_lo, y_hi):
        pad = 1.0 if y_lo == 0 else abs(y_lo) * 0.05
    else:
        pad = (y_hi - y_lo) * ylim_padding_frac

    y_min, y_max = y_lo - pad, y_hi + pad

    # Draw thresholds (they may be outside plot area; OK)
    if use_limits:
        ax.axhline(min_h, color="red", linestyle="--", alpha=0.5, label="Hard Min")
        ax.axhline(max_h, color="red", linestyle="--", alpha=0.5, label="Hard Max")
        ax.axhline(min_s, color="orange", linestyle=":", alpha=0.6, label="Soft Min")
        ax.axhline(max_s, color="orange", linestyle=":", alpha=0.6, label="Soft Max")
        ax.set_title(f"{title}\nHard: [{min_h}, {max_h}], Soft: [{min_s}, {max_s}]")
    else:
        ax.set_title(title)

    # IMPORTANT: lock y-lims to DATA range so thresholds never rescale the axis
    ax.set_ylim(y_min, y_max)

    # Legend
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        by_label = dict(zip(labels, handles, strict=False))
        ax.legend(by_label.values(), by_label.keys(), loc="upper right", fontsize=8)


def plot_soil_var(
    ax: "matplotlib.axes.Axes",
    var_key: str,
    title_prefix: str,
    plot_df: pd.DataFrame,
    var_config: dict,
    use_physical_limits: bool = True,
    ylim_padding_frac: float = 0.06,
) -> bool:
    """Draw multi-depth soil sensor profiles onto an existing axis.

    Looks up the column pattern from ``var_config[var_key]["pattern"]``
    and plots each depth as a separate line:

    - 15 cm  (blue)
    - 48 cm  (orange)
    - 80 cm  (green)
    - 200 cm (red)
    - 350 cm (purple)

    Expected column name format: ``{pattern}_{depth}_Avg_Soil``
    (e.g. ``SWC_15_Avg_Soil``).  Missing depths are silently skipped.

    Hard/soft threshold lines are drawn when ``use_physical_limits=True``.
    The y-axis is locked to the range of plotted data plus padding.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Axes to draw on.  Modified in place; returns a status boolean.
    var_key : str
        Key used to look up the variable's configuration in ``var_config``.
    title_prefix : str
        String prepended to the axis title (e.g. the site name or
        measurement period).
    plot_df : pd.DataFrame
        Data to plot.  Must contain:

        ``TIMESTAMP`` : pd.Timestamp
            Datetime column used for the x-axis.
        ``{pattern}_{depth}_Avg_Soil`` : numeric
            One column per depth that should be shown.
    var_config : dict
        Mapping ``{var_key: config_dict}``.  The ``config_dict`` may
        contain:

        ``"pattern"`` : str
            Column-name prefix (e.g. ``"SWC"``).
        ``"hard"`` : tuple of (float, float)
            Hard bounds; points outside are removed when
            ``use_physical_limits=True``.  Drawn as red dashed lines.
        ``"soft"`` : tuple of (float, float)
            Soft bounds drawn as orange dotted lines.
        ``"label"`` : str
            Y-axis label.
    use_physical_limits : bool, optional
        If ``True``, filter values outside hard bounds and draw threshold
        lines.  Default: ``True``.
    ylim_padding_frac : float, optional
        Fraction of data range added as padding.  Default: 0.06.

    Returns
    -------
    bool
        ``True`` if at least one depth was plotted; ``False`` if no data
        were available or ``var_key`` was not found in ``var_config``.

    Notes
    -----
    The legend uses up to 5 entries (one per depth) plus threshold lines,
    arranged in a single row with ``ncol=5`` to keep the axis compact.

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> from palmwtc.viz.qc_plots import plot_soil_var
    >>> fig, ax = plt.subplots()
    >>> has_data = plot_soil_var(ax, "SWC", "Soil Water Content", df, var_config)  # doctest: +SKIP

    See Also
    --------
    filter_plot : Two-chamber overlay for non-soil variables.
    """
    depths = ["15", "48", "80", "200", "350"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

    if var_key not in var_config:
        ax.set_title(f"{title_prefix} (config key '{var_key}' not found)")
        ax.grid(True, alpha=0.3)
        return False

    config = var_config[var_key]
    min_h, max_h = config.get("hard", (-np.inf, np.inf))
    min_s, max_s = config.get("soft", (-np.inf, np.inf))
    pattern = config.get("pattern", "")
    use_limits = bool(use_physical_limits)

    has_data = False
    y_series = []  # collect plotted data for y-limits

    for i, depth in enumerate(depths):
        col_name = f"{pattern}_{depth}_Avg_Soil"
        if col_name not in plot_df.columns:
            continue

        valid_data = plot_df[["TIMESTAMP", col_name]].dropna()

        # Filter outliers using HARD bounds if enabled (this REMOVES points)
        if use_limits:
            valid_data = valid_data[
                (valid_data[col_name] >= min_h) & (valid_data[col_name] <= max_h)
            ]

        if valid_data.empty:
            continue

        ax.plot(
            valid_data["TIMESTAMP"],
            valid_data[col_name],
            label=f"{depth}cm",
            color=colors[i],
            alpha=0.9,
            linewidth=1.5,
        )

        has_data = True
        y_series.append(valid_data[col_name].to_numpy())

    # Labels/grid/title
    ax.set_ylabel(config.get("label", ""), fontsize=14)
    ax.grid(True, alpha=0.3)

    if use_limits:
        ax.axhline(min_h, color="red", linestyle="--", alpha=0.5, label="Hard Min")
        ax.axhline(max_h, color="red", linestyle="--", alpha=0.5, label="Hard Max")
        ax.axhline(min_s, color="orange", linestyle=":", alpha=0.6, label="Soft Min")
        ax.axhline(max_s, color="orange", linestyle=":", alpha=0.6, label="Soft Max")
        ax.set_title(
            f"{title_prefix}\nHard: [{min_h}, {max_h}], Soft: [{min_s}, {max_s}]", fontsize=16
        )
    else:
        ax.set_title(f"{title_prefix}", fontsize=16)

    # If no plotted data, stop
    if not has_data or not y_series:
        return has_data

    # ----------------------------
    # Y-limits from ALL plotted data (no clipping)
    # ----------------------------
    y_all = np.concatenate(y_series)
    y_all = y_all[np.isfinite(y_all)]

    if y_all.size > 0:
        y_lo = np.nanmin(y_all)
        y_hi = np.nanmax(y_all)

        # Padding while preserving full data visibility
        if np.isclose(y_lo, y_hi):
            pad = 1.0 if y_lo == 0 else abs(y_lo) * 0.05
        else:
            pad = (y_hi - y_lo) * ylim_padding_frac

        ax.set_ylim(y_lo - pad, y_hi + pad)

    # Unique legend entries
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        by_label = dict(zip(labels, handles, strict=False))
        ax.legend(by_label.values(), by_label.keys(), loc="upper right", ncol=5, fontsize=12)

    return has_data


def plot_high_quality_timeseries(
    df: pd.DataFrame,
    var_name: str,
    qc_flag_col: str | None = None,
    title: str | None = None,
) -> None:
    """Line plot of Flag-0 (high-quality) data for one variable.

    Filters ``df`` to rows where the QC flag equals 0 and draws a single
    green line.  Calls :func:`matplotlib.pyplot.show` before returning.

    If the QC flag column is absent, all non-NaN data are plotted and a
    warning is printed.  If no Flag-0 data exist, a message is printed
    and the function returns without plotting.

    Parameters
    ----------
    df : pd.DataFrame
        QC-flagged DataFrame indexed by datetime.  Must contain:

        ``{var_name}`` : numeric
            Sensor values.
        ``{qc_flag_col}`` : int in {0, 1, 2}, optional
            QC flag column.  Falls back to all data if absent.
    var_name : str
        Name of the sensor variable column to plot.
    qc_flag_col : str, optional
        Name of the QC flag column.  Default: ``f"{var_name}_qc_flag"``.
    title : str, optional
        Axis title.  Default: ``f"High Quality Time Series: {var_name}"``.

    Returns
    -------
    None
        The figure is displayed via :func:`matplotlib.pyplot.show`.

    Notes
    -----
    Flag value 0 = Good (the only data shown in this plot).

    This function creates a new :func:`matplotlib.pyplot.figure` on each
    call; it does not return the figure object.  Use
    :func:`plot_drift_and_hq_timeseries` if you need a figure you can
    embed in a larger layout.

    Examples
    --------
    >>> from palmwtc.viz.qc_plots import plot_high_quality_timeseries
    >>> plot_high_quality_timeseries(df, "CO2_Avg")  # doctest: +SKIP

    See Also
    --------
    plot_drift_and_hq_timeseries : Two-panel version that also shows drift
        scores above the Flag-0 timeseries.
    """
    if var_name not in df.columns:
        print(f"Variable '{var_name}' not found in DataFrame.")
        return

    if qc_flag_col is None:
        qc_flag_col = f"{var_name}_qc_flag"

    if qc_flag_col not in df.columns:
        print(f"QC flag column '{qc_flag_col}' not found. Plotting all data.")
        valid_data = df
    else:
        # Filter for Flag 0 (High Quality)
        valid_data = df[df[qc_flag_col] == 0]

    if valid_data.empty:
        print(f"No high-quality data (Flag 0) found for {var_name}.")
        return

    plt.figure(figsize=(14, 6))
    plt.plot(
        valid_data.index,
        valid_data[var_name],
        label=f"{var_name} (Flag 0)",
        color="green",
        alpha=0.7,
        linewidth=1,
    )

    # Add title and labels
    plot_title = title if title else f"High Quality Time Series: {var_name}"
    plt.title(plot_title, fontsize=14)
    plt.xlabel("Date", fontsize=12)
    plt.ylabel(var_name, fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.tight_layout()
    plt.show()


def plot_drift_and_hq_timeseries(
    df: pd.DataFrame,
    var_name: str,
    drift_result: dict | pd.DataFrame | None,
    qc_flag_col: str | None = None,
) -> None:
    """Two-panel figure: drift score (top) and Flag-0 timeseries (bottom).

    Both panels share the same x-axis (time).  Calls
    :func:`matplotlib.pyplot.show` before returning.

    - **Top panel**: drift score line (purple) from ``drift_result``.
      A horizontal line at y=0 is drawn for reference.
    - **Bottom panel**: Flag-0 sensor values (green) from ``df``.

    If either panel has no data, a text annotation ("No Drift Data" /
    "No High Quality Data Found") is shown instead.

    Parameters
    ----------
    df : pd.DataFrame
        QC-flagged DataFrame indexed by datetime.  Must contain:

        ``{var_name}`` : numeric
            Sensor values.
        ``{qc_flag_col}`` : int in {0, 1, 2}, optional
            QC flag column.  If absent, all non-NaN data are used for
            the bottom panel.
    var_name : str
        Name of the sensor variable column.
    drift_result : dict or pd.DataFrame or None
        Drift detection output from
        :func:`palmwtc.qc.drift.detect_drift_windstats`.  Accepted
        forms:

        - ``dict`` with a ``"scores"`` key whose value is a DataFrame,
          a Series with a ``.to_pd()`` method, or a plain DataFrame.
        - A ``pd.DataFrame`` used directly as the drift score table.

        The expected column in the resolved DataFrame is
        ``f"{var_name}_drift_score"``.  Pass ``None`` to skip drift panel.
    qc_flag_col : str, optional
        QC flag column name.  Default: ``f"{var_name}_qc_flag"``.

    Returns
    -------
    None
        The figure is displayed via :func:`matplotlib.pyplot.show`.

    Notes
    -----
    Flag value 0 = Good (the only data shown in the bottom panel).

    Drift scores are produced by the windowed-statistics drift detector
    in :mod:`palmwtc.qc.drift`.  A score near 0 indicates stable sensor
    baseline; large deviations suggest drift.

    Examples
    --------
    >>> from palmwtc.viz.qc_plots import plot_drift_and_hq_timeseries
    >>> plot_drift_and_hq_timeseries(df, "CO2_Avg", drift_res)  # doctest: +SKIP

    See Also
    --------
    plot_baseline_drift : Daily-minimum view for long-term baseline drift.
    plot_high_quality_timeseries : Flag-0 only, no drift panel.
    """
    if drift_result is None:
        print(f"No drift result to plot for {var_name}")
        return

    # 1. Prepare Drift Data
    drift_df = pd.DataFrame()
    if isinstance(drift_result, dict):
        if "scores" in drift_result:
            scores = drift_result["scores"]
            if hasattr(scores, "to_pd"):
                drift_df = scores.to_pd()
            elif isinstance(scores, pd.DataFrame):
                drift_df = scores.copy()
            else:
                drift_df = pd.DataFrame(scores)

            drift_df.columns = [f"{var_name}_drift_score"]
    else:
        drift_df = drift_result

    # 2. Prepare HQ Data
    if qc_flag_col is None:
        qc_flag_col = f"{var_name}_qc_flag"

    hq_data = pd.DataFrame()
    if qc_flag_col in df.columns and var_name in df.columns:
        hq_data = df[df[qc_flag_col] == 0][[var_name]].dropna()
    else:
        if var_name in df.columns:
            # Fallback if no flag
            hq_data = df[[var_name]].dropna()

    # 3. Plotting
    if drift_df.empty and hq_data.empty:
        print(f"No data to visualize for {var_name}")
        return

    _fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    # Top Panel: Drift
    if not drift_df.empty:
        score_col = f"{var_name}_drift_score"
        if score_col in drift_df.columns:
            ax1.plot(
                drift_df.index,
                drift_df[score_col],
                color="#800080",
                linewidth=1.5,
                label="Drift Score",
            )
        ax1.axhline(y=0, color="k", linestyle="-", alpha=0.3)
        ax1.set_ylabel("Drift Score")
        ax1.set_title(f"Sensor Drift Detection: {var_name}", fontsize=12)
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc="upper right")
    else:
        ax1.text(0.5, 0.5, "No Drift Data", ha="center", va="center")

    # Bottom Panel: HQ Data
    if not hq_data.empty:
        ax2.plot(
            hq_data.index,
            hq_data[var_name],
            color="green",
            alpha=0.7,
            linewidth=1,
            label=f"{var_name} (Flag 0)",
        )
        ax2.set_ylabel(var_name)
        ax2.set_title(f"High Quality Time Series: {var_name}", fontsize=12)
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc="upper right")
    else:
        ax2.text(0.5, 0.5, "No High Quality Data Found", ha="center", va="center")

    ax2.set_xlabel("Date")
    plt.tight_layout()
    plt.show()


def visualize_drift(df: pd.DataFrame, drift_result: object, var_name: str) -> None:
    """Deprecated -- drift visualisation stub.

    This function previously visualised Merlion-based drift detection
    results.  The Merlion dependency was removed; calling this function
    prints a notice and returns immediately.

    Parameters
    ----------
    df : pd.DataFrame
        Ignored.
    drift_result : object
        Ignored.
    var_name : str
        Ignored.

    Returns
    -------
    None

    .. deprecated::
        Use :func:`plot_drift_and_hq_timeseries` with the windowed-statistics
        drift result from :mod:`palmwtc.qc.drift` instead.
    """
    print("  Drift visualization is no longer supported (Merlion dependency removed).")
    return


def plot_baseline_drift(baseline_df: pd.DataFrame, column: str, expected: float) -> None:
    """Line plot of daily minimum and mean values to check sensor baseline drift.

    Draws three elements on a single axis:

    1. **Daily minimum** (blue solid line): ``f"{column}_daily_min"`` column.
    2. **Daily mean** (green dashed line): ``f"{column}_daily_mean"`` column.
    3. **Expected baseline** (red dotted horizontal line) at ``expected`` with
       a shaded tolerance band of +/-50 ppm around it.

    Calls :func:`matplotlib.pyplot.show` before returning.

    Parameters
    ----------
    baseline_df : pd.DataFrame
        DataFrame indexed by date.  Must contain:

        ``{column}_daily_min`` : float
            Daily minimum values of the sensor.
        ``{column}_daily_mean`` : float
            Daily mean values of the sensor.
    column : str
        Sensor column base name (e.g. ``"CO2_Avg"``).  Used for axis
        labels and the title.
    expected : float
        Expected baseline concentration in ppm (e.g. 400 for ambient CO2).
        The tolerance band spans ``expected - 50`` to ``expected + 50``.

    Returns
    -------
    None
        The figure is displayed via :func:`matplotlib.pyplot.show`.

    Notes
    -----
    The +/-50 ppm tolerance band is hard-coded and is intended for CO2
    sensors (LI-COR LI-850).  For other variables the band width may not
    be meaningful.

    If ``{column}_daily_min`` is not present in ``baseline_df``, the plot
    is created but remains empty (no error is raised).

    Examples
    --------
    >>> from palmwtc.viz.qc_plots import plot_baseline_drift
    >>> plot_baseline_drift(baseline_df, "CO2_Avg", expected=400.0)  # doctest: +SKIP

    See Also
    --------
    plot_drift_and_hq_timeseries : Raw-resolution drift score + Flag-0 data.
    """
    _fig, ax = plt.subplots(figsize=(14, 5))

    min_col = f"{column}_daily_min"
    mean_col = f"{column}_daily_mean"

    if min_col in baseline_df.columns:
        ax.plot(baseline_df.index, baseline_df[min_col], "b-", label="Daily Minimum", alpha=0.8)
        ax.plot(baseline_df.index, baseline_df[mean_col], "g--", label="Daily Mean", alpha=0.6)
        ax.axhline(
            y=expected, color="red", linestyle=":", label=f"Expected baseline ({expected} ppm)"
        )
        ax.fill_between(
            baseline_df.index,
            expected - 50,
            expected + 50,
            color="red",
            alpha=0.1,
            label="±50 ppm tolerance",
        )

    ax.set_xlabel("Date")
    ax.set_ylabel(f"{column} (ppm)")
    ax.set_title(f"Baseline Drift Detection: {column}")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def plot_breakpoints_analysis(
    df: pd.DataFrame,
    var_name: str,
    breakpoint_result: dict | None,
    qc_flag_col: str | None = None,
    figsize: tuple[float, float] = (16, 10),
    max_table_rows: int = 15,
    min_confidence: float = 0.0,
    show_all_breakpoints: bool = False,
) -> "tuple[matplotlib.figure.Figure, matplotlib.figure.Figure] | tuple[None, None]":
    """Two-figure breakpoint analysis: annotated timeseries + breakpoint table.

    **Figure 1 -- Analysis plot** (2x2 grid):

    - **Panel 1 (top, full width)**: Flag-0 sensor timeseries (green)
      with vertical dashed lines at each breakpoint, coloured by index
      using the ``Set1`` colormap.  A diamond marker is placed on the
      series at each breakpoint timestamp.  Horizontal red lines show the
      segment mean for each interval between breakpoints.  Downsampled to
      50 000 points for performance when the dataset is larger.
    - **Panel 2 (bottom-left)**: Bar chart of segment means with +/-1 SD
      error bars.
    - **Panel 3 (bottom-right)**: Bar chart of breakpoint confidence
      scores (0-1).  An orange dashed line at 0.5 marks a rough
      "moderate confidence" threshold.

    **Figure 2 -- Table plot**: plain matplotlib table listing breakpoint
    number, timestamp (``YYYY-MM-DD HH:MM``), and confidence with a
    "Robust / Moderate / Weak" label (>= 0.7 / >= 0.4 / < 0.4).  Up to
    ``max_table_rows`` rows; additional rows replaced with ``"..."`` if
    the list is truncated.  The table always shows all raw breakpoints
    (ignoring ``min_confidence``).

    Parameters
    ----------
    df : pd.DataFrame
        QC-flagged DataFrame indexed by datetime.  Must contain:

        ``{var_name}`` : numeric
            Sensor values.
        ``{qc_flag_col}`` : int in {0, 1, 2}, optional
            QC flag column.  Only Flag-0 rows are plotted.  If absent,
            all non-NaN values are used.
    var_name : str
        Name of the sensor variable column.
    breakpoint_result : dict or None
        Breakpoint detection output from
        :func:`palmwtc.qc.breakpoints.detect_breakpoints_ruptures`.
        Expected keys:

        ``"breakpoints"`` : list of pd.Timestamp
            Detected breakpoint timestamps.
        ``"confidence_scores"`` : list of float
            Confidence score (0-1) per breakpoint.
        ``"segment_info"`` : list of dict
            Each dict has keys ``"mean"``, ``"std"``, ``"start"``,
            ``"end"``.
        ``"n_breakpoints"`` : int
            Total breakpoint count (used when ``show_all_breakpoints``
            is ``True``).

        Pass ``None`` to get ``(None, None)`` back.
    qc_flag_col : str, optional
        QC flag column name.  Default: ``f"{var_name}_qc_flag"``.
    figsize : tuple of (float, float), optional
        Size of Figure 1 (the analysis plot).  Default: ``(16, 10)``.
    max_table_rows : int, optional
        Maximum rows in the table figure.  Default: 15.
    min_confidence : float, optional
        Minimum confidence score for breakpoints shown in Figure 1.
        Ignored when ``show_all_breakpoints=True``.  Default: 0.0
        (show all).
    show_all_breakpoints : bool, optional
        If ``True``, ignore ``min_confidence`` and plot every breakpoint
        in Figure 1.  Default: ``False``.

    Returns
    -------
    tuple of (matplotlib.figure.Figure, matplotlib.figure.Figure)
        ``(fig_analysis, fig_table)`` -- the two figures.
    tuple of (None, None)
        Returned when ``breakpoint_result`` is ``None`` or no data are
        available for the variable.

    Notes
    -----
    Confidence score thresholds used in the table label:

    - >= 0.7 = "Robust"
    - >= 0.4 = "Moderate"
    - < 0.4  = "Weak"

    Breakpoint detection uses the ``ruptures`` library (L2 cost, PELT
    algorithm).  See :func:`palmwtc.qc.breakpoints.detect_breakpoints_ruptures`
    for details.

    Examples
    --------
    >>> from palmwtc.viz.qc_plots import plot_breakpoints_analysis
    >>> fig1, fig2 = plot_breakpoints_analysis(df, "CO2_Avg", bp_result)  # doctest: +SKIP

    See Also
    --------
    visualize_breakpoints : Three-panel overview with kept/ignored
        distinction, intended for interactive inspection.
    palmwtc.qc.breakpoints.detect_breakpoints_ruptures : Produces the
        ``breakpoint_result`` dict.
    """
    if breakpoint_result is None:
        print(f"No breakpoint result to plot for {var_name}")
        return None, None

    # Prepare data
    if qc_flag_col is None:
        qc_flag_col = f"{var_name}_qc_flag"

    # Filter to high-quality data if QC flags provided
    if qc_flag_col in df.columns and var_name in df.columns:
        df_filtered = df[df[qc_flag_col] == 0][[var_name]].dropna()
        data_label = f"{var_name} (Flag 0)"
    else:
        df_filtered = df[[var_name]].dropna() if var_name in df.columns else pd.DataFrame()
        data_label = var_name

    if df_filtered.empty:
        print(f"No data to visualize for {var_name}")
        return None

    # Extract breakpoint information
    raw_breakpoints = breakpoint_result.get("breakpoints", [])
    raw_confidence = breakpoint_result.get("confidence_scores", [])
    segment_info = breakpoint_result.get("segment_info", [])

    # Filter based on confidence
    breakpoints = []
    confidence_scores = []

    if min_confidence > 0 and not show_all_breakpoints:
        for bp, conf in zip(raw_breakpoints, raw_confidence, strict=False):
            if conf >= min_confidence:
                breakpoints.append(bp)
                confidence_scores.append(conf)
        n_breakpoints = len(breakpoints)
        print(
            f"  Filtering breakpoints: showing {n_breakpoints}/{len(raw_breakpoints)} (conf >= {min_confidence})"
        )
    else:
        breakpoints = raw_breakpoints
        confidence_scores = raw_confidence
        n_breakpoints = breakpoint_result.get("n_breakpoints", 0)

    # --- Figure 1: Analysis Plots ---
    fig_analysis = plt.figure(figsize=figsize)
    gs = fig_analysis.add_gridspec(2, 2, height_ratios=[2, 1], hspace=0.3, wspace=0.3)

    # Panel 1: Time series with breakpoints (spans both columns)
    ax1 = fig_analysis.add_subplot(gs[0, :])

    # Downsample for plotting if dataset is too large (speeds up matplotlib significantly)
    max_plot_points = 50000
    if len(df_filtered) > max_plot_points:
        step = len(df_filtered) // max_plot_points
        df_plot = df_filtered.iloc[::step]
        print(
            f"  Note: Downsampled plot from {len(df_filtered)} to {len(df_plot)} points for performance."
        )
    else:
        df_plot = df_filtered

    ax1.plot(
        df_plot.index,
        df_plot[var_name],
        color="#2ca02c",
        alpha=0.6,
        linewidth=1,
        label=data_label,
        zorder=1,
    )

    # Add vertical lines at breakpoints with labels
    colors_bp = plt.cm.Set1(np.linspace(0, 1, max(n_breakpoints, 1)))
    for i, (bp_time, conf) in enumerate(zip(breakpoints, confidence_scores, strict=False)):
        # Vertical line
        ax1.axvline(
            x=bp_time,
            color=colors_bp[i],
            linestyle="--",
            linewidth=2.5,
            alpha=0.9,
            label=f"BP {i + 1} (conf: {conf:.2f})",
            zorder=3,
        )

        # Add a marker at the breakpoint on the data line
        # Find the closest data point to the breakpoint
        if bp_time in df_filtered.index:
            y_val = df_filtered.loc[bp_time, var_name]
        else:
            # Find nearest timestamp
            idx = df_filtered.index.get_indexer([bp_time], method="nearest")[0]
            y_val = df_filtered.iloc[idx][var_name] if idx < len(df_filtered) else None

        if y_val is not None and not pd.isna(y_val):
            ax1.scatter(
                [bp_time],
                [y_val],
                color=colors_bp[i],
                s=150,
                marker="D",
                edgecolors="black",
                linewidths=2,
                zorder=4,
                label=f"_BP{i + 1}_marker",
            )  # underscore prefix hides from legend

    # Add segment means as horizontal lines
    for i, seg in enumerate(segment_info):
        ax1.hlines(
            y=seg["mean"],
            xmin=seg["start"],
            xmax=seg["end"],
            colors="red",
            linestyles="-",
            linewidth=2.5,
            alpha=0.5,
            zorder=2,
            label="Segment Mean" if i == 0 else "",
        )

    ax1.set_ylabel(var_name, fontsize=12)
    ax1.set_title(
        f"Breakpoint Detection: {var_name}\n{n_breakpoints} breakpoint(s) shown",
        fontsize=14,
        fontweight="bold",
    )
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="best", fontsize=9, ncol=2)

    # Panel 2: Segment means bar chart (left)
    ax2 = fig_analysis.add_subplot(gs[1, 0])
    if segment_info:
        segment_labels = [f"Seg {i + 1}" for i in range(len(segment_info))]
        segment_means = [seg["mean"] for seg in segment_info]
        segment_stds = [seg["std"] for seg in segment_info]

        bars = ax2.bar(segment_labels, segment_means, color="#1f77b4", alpha=0.7, edgecolor="black")
        ax2.errorbar(
            segment_labels,
            segment_means,
            yerr=segment_stds,
            fmt="none",
            ecolor="red",
            capsize=5,
            alpha=0.6,
        )

        # Add value labels on bars
        for bar, mean, std in zip(bars, segment_means, segment_stds, strict=False):
            height = bar.get_height()
            ax2.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{mean:.2f}\n±{std:.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold",
            )

        ax2.set_ylabel(f"{var_name} Mean", fontsize=11)
        ax2.set_ylabel(f"{var_name} Mean", fontsize=11)
        ax2.set_title("Segment Means (±1 SD)", fontsize=12, fontweight="bold")
        ax2.grid(True, alpha=0.3, axis="y")
    else:
        ax2.text(0.5, 0.5, "No segments", ha="center", va="center", fontsize=12)
        ax2.set_title("Segment Means", fontsize=12, fontweight="bold")

    # Panel 3: Confidence scores bar chart (right)
    ax3 = fig_analysis.add_subplot(gs[1, 1])
    if confidence_scores:
        bp_labels = [f"BP {i + 1}" for i in range(len(confidence_scores))]
        bars = ax3.bar(
            bp_labels,
            confidence_scores,
            color=colors_bp[: len(confidence_scores)],
            alpha=0.7,
            edgecolor="black",
        )

        # Add value labels
        for bar, conf in zip(bars, confidence_scores, strict=False):
            height = bar.get_height()
            ax3.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{conf:.3f}",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )

        ax3.set_ylabel("Confidence Score", fontsize=11)
        ax3.set_ylim(0, 1.1)
        ax3.axhline(y=0.5, color="orange", linestyle="--", alpha=0.5, linewidth=1)
        ax3.set_title("Breakpoint Confidence Scores", fontsize=12, fontweight="bold")
        ax3.grid(True, alpha=0.3, axis="y")
    else:
        ax3.text(0.5, 0.5, "No confidence scores", ha="center", va="center", fontsize=12)
        ax3.set_title("Breakpoint Confidence Scores", fontsize=12, fontweight="bold")

    plt.tight_layout()

    # --- Figure 2: Table ---
    fig_table = plt.figure(figsize=(10, max(4, len(breakpoints) * 0.4)))
    ax_table = fig_table.add_subplot(111)
    ax_table.axis("off")

    # Prepare table data
    table_data = []

    # Use all breakpoints for table if they exist, to show full context
    # Or use the filtered list if that's what is plotted (user choice)
    # The requirement was "Second frame is Breakpoint timestamps. This time you can include alll of the breakpoint"

    display_breakpoints = raw_breakpoints
    display_confidence = raw_confidence

    if display_breakpoints:
        for i, (bp, conf) in enumerate(zip(display_breakpoints, display_confidence, strict=False)):
            if i >= max_table_rows:
                table_data.append(["...", "...", "..."])
                break

            # Highlight robust breakpoints
            status = "Robust" if conf >= 0.7 else "Moderate" if conf >= 0.4 else "Weak"
            table_data.append(
                [f"BP {i + 1}", bp.strftime("%Y-%m-%d %H:%M"), f"{conf:.3f} ({status})"]
            )

        columns = ["Breakpoint", "Timestamp", "Confidence"]
        tbl = ax_table.table(cellText=table_data, colLabels=columns, loc="center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(10)
        tbl.scale(1, 1.5)

        # Style header
        for (row, _col), cell in tbl.get_celld().items():
            if row == 0:
                cell.set_text_props(weight="bold")
                cell.set_facecolor("#e6e6e6")
    else:
        ax_table.text(0.5, 0.5, "No breakpoints detected", ha="center", va="center", fontsize=12)

    # ax_table.set_title(f"Detected Breakpoints List ({len(display_breakpoints)} Total)", fontsize=14, fontweight='bold')
    plt.tight_layout()

    return fig_analysis, fig_table


def visualize_missing_data(
    df: pd.DataFrame,
    var_name: str,
    frequency_seconds: float | None = None,
    config: dict | None = None,
    figsize: tuple[float, float] = (15, 8),
) -> "matplotlib.figure.Figure | None":
    """Two-panel figure showing data availability and gap distribution.

    Identifies timestamps where the interval between consecutive valid
    readings exceeds ``2.5 * frequency_seconds`` (a "gap") and plots:

    - **Top panel** (3:1 height ratio): raw sensor timeseries (blue line)
      with the title showing the sampling frequency, data coverage, and
      missing-data percentage.  Downsampled to 50 000 points when the
      series is longer.
    - **Bottom panel**: bar chart of gap duration in hours vs time, one
      bar per detected gap.  Uses log scale on the y-axis when any gap
      exceeds 1 hour.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with a datetime index.  Must contain:

        ``{var_name}`` : numeric
            Sensor values.  NaN rows are treated as missing.
    var_name : str
        Name of the sensor variable column.
    frequency_seconds : float, optional
        Expected sampling interval in seconds (e.g. 4.0 for a 4 s LI-850
        stream).  If ``None``, the function looks up
        ``config[key]["measurement_frequency"]``; if still not found,
        defaults to 4.0 seconds with a warning printed to stdout.
    config : dict, optional
        Variable configuration dict (same structure as ``var_config``
        used elsewhere).  Searched for ``var_name`` by direct key match,
        ``"columns"`` list membership, or ``"pattern"`` prefix.
    figsize : tuple of (float, float), optional
        Figure width and height in inches.

    Returns
    -------
    matplotlib.figure.Figure or None
        The figure, or ``None`` if ``var_name`` is not in ``df`` or no
        valid data points exist.

    Notes
    -----
    Gap detection threshold: a gap is counted when the time between two
    consecutive non-NaN records exceeds ``2.5 * frequency_seconds``.
    This allows for small timing jitter without false positives.

    The missing-data percentage shown in the title is estimated as::

        missing_pct = (expected_points - actual_points) / expected_points * 100

    where ``expected_points = total_duration_sec / frequency_seconds``.

    Examples
    --------
    >>> from palmwtc.viz.qc_plots import visualize_missing_data
    >>> fig = visualize_missing_data(df, "CO2_Avg", frequency_seconds=4.0)  # doctest: +SKIP

    See Also
    --------
    visualize_qc_flags : Per-rule flag scatter, useful after gaps are
        already filled or excluded.
    """

    if var_name not in df.columns:
        print(f"Variable '{var_name}' not found in DataFrame.")
        return None

    # Determine frequency
    freq = frequency_seconds

    if freq is None and config:
        # Try finding the key for this variable
        found_key = None
        if var_name in config:
            found_key = var_name
        else:
            # Search by columns or pattern
            for key, props in config.items():
                if "columns" in props and var_name in props["columns"]:
                    found_key = key
                    break
                if "pattern" in props and var_name.startswith(props["pattern"]):
                    found_key = key
                    break

        if found_key:
            freq = config[found_key].get("measurement_frequency")
            # Debug
            # print(f"Resolved {var_name} to config key '{found_key}', freq={freq}")

    if freq is None:
        # Default to 4s as per analysis if not found, but this likely means look up failed
        print(f"Warning: No frequency specified for {var_name}. Defaulting to 4.0 seconds.")
        freq = 4.0

    # Get valid data
    valid_data = df[[var_name]].dropna().sort_index()

    if valid_data.empty:
        print(f"No data found for {var_name}.")
        return None

    # Calculate gaps
    # A gap is defined as difference > 2.5 * frequency (allowing some jitter)
    diffs = valid_data.index.to_series().diff().dt.total_seconds()
    gap_threshold = freq * 2.5

    # Store gaps (timestamp indicates END of gap)
    gaps = diffs[diffs > gap_threshold]

    # Summary Props
    if not valid_data.empty:
        total_duration_sec = (valid_data.index.max() - valid_data.index.min()).total_seconds()
        expected_points = total_duration_sec / freq
        actual_points = len(valid_data)
        missing_points = max(0, expected_points - actual_points)
        missing_pct = (
            (missing_points / expected_points * 100)
            if expected_points > 0 and total_duration_sec > 0
            else 0
        )
    else:
        missing_pct = 100.0

    # Plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, height_ratios=[3, 1], sharex=True)

    # Ax1: Time Series with Gaps Highlighted
    # Downsample for plotting if needed
    if len(valid_data) > 50000:
        plot_data = valid_data.iloc[:: int(len(valid_data) / 50000)]
    else:
        plot_data = valid_data

    ax1.plot(
        plot_data.index,
        plot_data[var_name],
        label="Observed Data",
        color="blue",
        linewidth=0.5,
        alpha=0.7,
    )

    ax1.set_ylabel(var_name)
    ax1.set_title(
        f"Data Availability: {var_name}\\nFreq: {freq}s | Coverage: {100 - missing_pct:.1f}% | Missing: {missing_pct:.1f}%",
        fontsize=14,
        fontweight="bold",
    )

    ax1.legend(loc="upper right")
    ax1.grid(True, alpha=0.3)

    # Ax2: Gap Size vs Time
    if not gaps.empty:
        gap_hours = gaps / 3600.0
        # Check max gap size for scaling
        max_gap = gap_hours.max()

        ax2.bar(
            gaps.index, gap_hours, width=0.01, color="red", alpha=0.6, label="Gap Duration (hrs)"
        )
        ax2.set_ylabel("Gap Size (Hours)")

        # Use log scale if gaps vary wildly
        if max_gap > 1.0:  # If we have gaps > 1 hour
            ax2.set_yscale("log")
            ax2.set_title("Gap Distribution over Time (Log Scale)", fontsize=12)
        else:
            ax2.set_title("Gap Distribution over Time", fontsize=12)

        ax2.grid(True, alpha=0.3)
    else:
        ax2.text(0.5, 0.5, "No significant gaps detected", ha="center", va="center")

    plt.xlabel("Date")
    plt.tight_layout()
    return fig


def visualize_breakpoints(
    df: pd.DataFrame,
    var_name: str,
    bp_result: dict,
    filtered_bps: list | None = None,
    title_suffix: str = "",
) -> None:
    """Three-panel overview of breakpoints with kept/ignored distinction.

    Plots a 3x1 figure (shared x-axis, monthly tick marks) and prints a
    summary table to stdout.  Calls :func:`matplotlib.pyplot.show` before
    returning.

    - **Panel 1 (top)**: hourly-resampled sensor timeseries (blue line)
      with vertical lines at each breakpoint.  Breakpoints in
      ``filtered_bps`` are drawn solid green (kept); all others are drawn
      dashed red (ignored).
    - **Panel 2 (middle)**: segment means as horizontal coloured lines,
      one colour per segment (``Set3`` colormap).  Mean values are
      annotated above each line.
    - **Panel 3 (bottom)**: bar chart of confidence scores, one orange
      bar per breakpoint.

    After showing the plot, a text table is printed to stdout with columns:
    ``#``, ``Date``, ``Confidence``, ``Prev Mean``, ``New Mean``,
    ``Shift``.  Shows up to 20 breakpoints.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame indexed by datetime.  Must contain:

        ``{var_name}`` : numeric
            Raw sensor values.  Resampled to 1-hour mean for plotting.
    var_name : str
        Name of the sensor variable column.
    bp_result : dict
        Breakpoint detection output from
        :func:`palmwtc.qc.breakpoints.detect_breakpoints_ruptures`.
        Expected keys:

        ``"n_breakpoints"`` : int
            Total number of detected breakpoints.
        ``"breakpoints"`` : list of pd.Timestamp
            Breakpoint timestamps.
        ``"segment_info"`` : list of dict
            Each dict has keys ``"mean"``, ``"std"``, ``"start"``,
            ``"end"``.
        ``"confidence_scores"`` : list of float
            Confidence score per breakpoint.
    filtered_bps : list of pd.Timestamp, optional
        Subset of breakpoints to mark as "kept" (green solid lines).
        Breakpoints not in this list are drawn red dashed.  If ``None``,
        all breakpoints are drawn red dashed.
    title_suffix : str, optional
        Extra text appended to Panel 1's title (e.g. a date range or
        site label).

    Returns
    -------
    None
        The figure is displayed via :func:`matplotlib.pyplot.show` and
        a summary table is printed to stdout.

    Notes
    -----
    The data is resampled to 1-hour means before plotting so that very
    high-frequency streams (e.g. 4-second LI-850 data) render in a
    reasonable time without explicit downsampling.

    The ``{var_name} (ppm)`` label is used literally on the y-axis of
    Panel 1, so it is most appropriate for CO2 and H2O concentration
    variables.

    Examples
    --------
    >>> from palmwtc.viz.qc_plots import visualize_breakpoints
    >>> visualize_breakpoints(df, "CO2_Avg", bp_result, filtered_bps=kept)  # doctest: +SKIP

    See Also
    --------
    plot_breakpoints_analysis : Two-figure version with a table figure and
        confidence-filtered plotting.
    palmwtc.qc.breakpoints.detect_breakpoints_ruptures : Produces the
        ``bp_result`` dict.
    """
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    if bp_result is None or bp_result["n_breakpoints"] == 0:
        print(f"No breakpoints to visualize for {var_name}")
        return

    _fig, axes = plt.subplots(3, 1, figsize=(16, 12), sharex=True)

    # Downsample data for plotting
    plot_data = df[var_name].dropna().resample("1h").mean()

    # Panel 1: Time series with breakpoints
    ax1 = axes[0]
    ax1.plot(plot_data.index, plot_data.values, "b-", alpha=0.7, linewidth=0.5)

    # Color segments differently
    breakpoints = bp_result["breakpoints"]
    segment_info = bp_result.get("segment_info", [])
    confidence_scores = bp_result.get("confidence_scores", [])

    colors = plt.cm.Set3(range(len(breakpoints) + 1))

    for bp in breakpoints:
        is_kept = filtered_bps is not None and bp in filtered_bps
        color = "green" if is_kept else "red"
        style = "-" if is_kept else "--"
        width = 2.5 if is_kept else 1.0
        alpha = 1.0 if is_kept else 0.4

        ax1.axvline(bp, color=color, linestyle=style, alpha=alpha, linewidth=width)

    ax1.set_ylabel(f"{var_name} (ppm)")
    ax1.set_title(
        f"{var_name} Mean Shifts (L2): Green = KEPT, Red = IGNORED {title_suffix}\n({len(breakpoints)} breakpoints detected)"
    )
    ax1.grid(True, alpha=0.3)

    # Panel 2: Segment means
    ax2 = axes[1]
    if segment_info:
        for i, seg in enumerate(segment_info):
            ax2.hlines(
                seg["mean"],
                seg["start"],
                seg["end"],
                colors=colors[i % len(colors)],
                linewidth=3,
                alpha=0.8,
            )
            # Add mean value label
            mid_time = seg["start"] + (seg["end"] - seg["start"]) / 2
            ax2.annotate(
                f"{seg['mean']:.1f}",
                (mid_time, seg["mean"]),
                textcoords="offset points",
                xytext=(0, 5),
                ha="center",
                fontsize=8,
            )

    ax2.set_ylabel("Segment Mean")
    ax2.set_title("Segment Means (Use to identify major drift events)")
    ax2.grid(True, alpha=0.3)

    # Panel 3: Confidence scores
    ax3 = axes[2]
    if confidence_scores and len(breakpoints) > 0:
        # Plot confidence at each breakpoint
        bp_times = breakpoints[: len(confidence_scores)]
        ax3.bar(bp_times, confidence_scores, width=5, color="orange", alpha=0.7)

        ax3.set_ylabel("Confidence Score")
        ax3.set_xlabel("Date")
        ax3.set_title("Breakpoint Confidence Scores (Higher = more significant shift)")
        ax3.set_ylim(0, 1.1)
        ax3.grid(True, alpha=0.3)

    # Format x-axis
    ax3.xaxis.set_major_locator(mdates.MonthLocator())
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=45)

    plt.tight_layout()
    plt.show()

    # Print summary table
    print(f"\n{'=' * 80}")
    print(f"BREAKPOINT SUMMARY FOR {var_name}")
    print(f"{'=' * 80}")
    print(
        f"{'#':<5} {'Date':<20} {'Confidence':<12} {'Prev Mean':<12} {'New Mean':<12} {'Shift':<10}"
    )
    print(f"{'-' * 80}")

    for i, bp in enumerate(breakpoints[:20]):  # Show max 20
        conf = confidence_scores[i] if i < len(confidence_scores) else "N/A"
        if segment_info and i < len(segment_info) - 1:
            prev_mean = segment_info[i]["mean"]
            new_mean = segment_info[i + 1]["mean"]
            shift = new_mean - prev_mean
            print(
                f"{i + 1:<5} {str(bp)[:19]:<20} {conf:<12.2f} {prev_mean:<12.1f} {new_mean:<12.1f} {shift:+.1f}"
            )
        else:
            print(f"{i + 1:<5} {str(bp)[:19]:<20} {conf}")

    if len(breakpoints) > 20:
        print(f"... and {len(breakpoints) - 20} more breakpoints")
    print(f"{'=' * 80}")
