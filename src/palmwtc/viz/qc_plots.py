"""
Visualization functions for quality control flags.

Note: Visualization functions are deterministic and do not require random seeds.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def visualize_qc_flags(df, var_name, qc_results, config=None, figsize=(15, 20)):
    """
    Visualize QC flags for a variable with detailed breakdown by method.

    Creates a multi-panel figure showing:
    1. Overall Time series with combined QC flags
    2. Separate Time series for each active QC method (Bounds, Merlion, etc.)
    3. Summary statistics (Counts and Breakdown)

    Parameters:
    -----------
    df : pd.DataFrame
        Data containing the variable and QC flags
    var_name : str
        Variable column name
    qc_results : dict
        QC results for this variable from process_variable_qc()
    config : dict, optional
        Variable configuration (for labels and bounds)
    figsize : tuple
        Figure size as (width, height)

    Returns:
    --------
    fig : matplotlib.figure.Figure
        The created figure
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


def plot_qc_comparison(df, var_names, qc_results, figsize=None):
    """
    Compare QC statistics across multiple variables.

    Parameters:
    -----------
    df : pd.DataFrame
        Data containing variables
    var_names : list
        List of variable names to compare
    qc_results : dict
        Dictionary of QC results for all variables
    figsize : tuple, optional
        Figure size. If None, calculated based on number of variables.

    Returns:
    --------
    fig : matplotlib.figure.Figure
        The created figure
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


def plot_qc_summary_heatmap(qc_results, figsize=(14, 10)):
    """
    Create a heatmap showing QC statistics for all variables.

    Parameters:
    -----------
    qc_results : dict
        Dictionary of QC results for all variables
    figsize : tuple
        Figure size

    Returns:
    --------
    fig : matplotlib.figure.Figure
        The created figure
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
    ax, df_, col_c1, col_c2, var_key, var_config, use_physical_limits=True, ylim_padding_frac=0.06
):
    """
    Helper function to plot chamber comparison for a given variable key.

    Args:
        ax: Matplotlib axes object
        df_: DataFrame containing data
        col_c1: Column name for Chamber 1
        col_c2: Column name for Chamber 2
        var_key: Variable key in configuration
        var_config: Variable configuration dictionary
        use_physical_limits: Boolean to enable/disable physical limits filtering
        ylim_padding_frac: Padding fraction for y-axis limits (default 0.06)
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
    ax, var_key, title_prefix, plot_df, var_config, use_physical_limits=True, ylim_padding_frac=0.06
):
    """
    Helper function to plot soil variables at different depths.

    Args:
        ax: Matplotlib axes object
        var_key: Variable key in configuration
        title_prefix: Title prefix
        plot_df: DataFrame containing the data to plot
        var_config: Variable configuration dictionary
        use_physical_limits: Boolean to enable/disable physical limits filtering
        ylim_padding_frac: Padding fraction for y-axis limits (default 0.06)

    Returns:
        Boolean indicating if data was plotted
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


def plot_high_quality_timeseries(df, var_name, qc_flag_col=None, title=None):
    """
    Plot time series data for a variable, filtering for high quality (Flag 0).

    Args:
        df: DataFrame containing the data
        var_name: Name of the variable to plot
        qc_flag_col: Name of the quality flag column (optional).
                     If None, defaults to f"{var_name}_qc_flag".
        title: Custom title for the plot (optional)
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


def plot_drift_and_hq_timeseries(df, var_name, drift_result, qc_flag_col=None):
    """
    Plot drift detection results and high-quality time series in faceted subplots sharing x-axis.

    Args:
        df: DataFrame containing the data
        var_name: Name of the variable to plot
        drift_result: Result object/dict from detect_drift_windstats
        qc_flag_col: Name of the quality flag column (optional).
                     If None, defaults to f"{var_name}_qc_flag".
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


def visualize_drift(df, drift_result, var_name):
    """
    Deprecated: Drift detection using Merlion has been removed.
    """
    print("  Drift visualization is no longer supported (Merlion dependency removed).")
    return


def plot_baseline_drift(baseline_df: pd.DataFrame, column: str, expected: float):
    """Plot daily minimum values to visualize sensor drift."""
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
    df,
    var_name,
    breakpoint_result,
    qc_flag_col=None,
    figsize=(16, 10),
    max_table_rows=15,
    min_confidence=0.0,
    show_all_breakpoints=False,
):
    """
    Visualize breakpoint detection results with clear timestamps and confidence scores.

    Creates two figures:
    1. Analysis Plot: Time series with breakpoints, segment means, and confidence scores.
    2. Table Plot: Detailed table of breakpoint timestamps and statistics.

    Args:
        df: DataFrame containing the data
        var_name: Name of the variable to plot
        breakpoint_result: Result dict from detect_breakpoints_ruptures
        qc_flag_col: Name of the quality flag column (optional).
        figsize: Figure size for the analysis plot
        max_table_rows: Maximum number of breakpoint rows to render in the table
        min_confidence: Threshold for filtering breakpoints in the plots (if show_all_breakpoints is False)
        show_all_breakpoints: If True, ignore min_confidence for plotting breakpoints

    Returns:
        tuple: (fig_analysis, fig_table) - Two matplotlib figure objects
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


def visualize_missing_data(df, var_name, frequency_seconds=None, config=None, figsize=(15, 8)):
    """
    Visualize missing data gaps based on expected measurement frequency.

    This function identifies time intervals where data is missing (gap > 2.5 * frequency)
    and visualizes them alongside the available data points.

    Args:
        df: DataFrame with datetime index.
        var_name: Variable name to check.
        frequency_seconds: Expected sampling interval in seconds.
                           If None, tries to read from config.
        config: Optional variable config dictionary (VAR_CONFIG).
        figsize: Figure size.

    Returns:
        fig: Matplotlib figure
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


def visualize_breakpoints(df, var_name, bp_result, filtered_bps=None, title_suffix=""):
    """
    Create an interactive visualization of detected breakpoints with segment info.
    Helps identify which breakpoints are major drift events.
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
