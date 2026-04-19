"""
Timeseries / aggregate flux plots for palmwtc.

Ported verbatim from ``flux_chamber/src/flux_visualization.py``.

Public API (matplotlib only, static figures):

- ``plot_tropical_seasonal_diurnal`` — diurnal cycles split by Wet vs Dry season.
- ``plot_flux_heatmap`` — Hour-of-day vs Month-Year heatmap, 3 subplots.
- ``plot_flux_vs_tree_age`` — flux vs tree age in years, faceted by chamber.
- ``plot_concentration_slope_vs_tree_age`` — pure ppm/s slope vs tree age.

Also includes the additional matplotlib helpers from the source module
that have no current notebook callers but are kept for parity:

- ``plot_flux_timeseries_tiers``
- ``plot_cumulative_flux_with_gaps``
- ``plot_cumulative_flux_by_date``
- ``plot_flux_boxplot_vs_tree_age``
- ``plot_concentration_slope_boxplot_vs_tree_age``
- ``plot_flux_monthly_boxplot``

The Plotly-based ``plot_concentration_slope_vs_date_interactive`` is NOT
ported here; per the Phase 2 plan, Plotly figures live in
``palmwtc.viz.interactive``.
"""

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def plot_flux_timeseries_tiers(
    flux_df, variable="flux_absolute", title="CO2 Flux Timeseries by QC Tier"
):
    """
    Plots flux timeseries with 3 filtered views (Tier 1: All, Tier 2: Flag 0+1, Tier 3: Flag 0).
    Faceted by Chamber (Columns) and Tier (Rows).
    """
    if flux_df.empty:
        return

    chambers = sorted(flux_df["Source_Chamber"].unique())
    n_chambers = len(chambers)

    # Tier definitions
    tiers = [
        ("Tier 1: All Data (Flags 0, 1, 2)", lambda df: df),
        ("Tier 2: High + Medium Quality (Flags 0, 1)", lambda df: df[df["qc_flag"] <= 1]),
        ("Tier 3: High Quality Only (Flag 0)", lambda df: df[df["qc_flag"] == 0]),
    ]

    fig, axes = plt.subplots(3, n_chambers, sharex=True, sharey=False, figsize=(8 * n_chambers, 12))
    # If only 1 chamber, axes is 1D array. if multiple, 2D. Ensure 2D for consistency.
    if n_chambers == 1:
        axes = np.array([[ax] for ax in axes])

    # Store min/max for each tier to unify limits later
    tier_limits = {i: [float("inf"), float("-inf")] for i in range(3)}

    for col_idx, chamber in enumerate(chambers):
        chamber_data = flux_df[flux_df["Source_Chamber"] == chamber]

        for row_idx, (tier_name, tier_func) in enumerate(tiers):
            tier_data = tier_func(chamber_data)
            ax = axes[row_idx, col_idx]

            # Update min/max for this tier row
            if not tier_data.empty:
                t_min, t_max = tier_data[variable].min(), tier_data[variable].max()
                tier_limits[row_idx][0] = min(tier_limits[row_idx][0], t_min)
                tier_limits[row_idx][1] = max(tier_limits[row_idx][1], t_max)

            # Color by QC Flag if mixed, else Green for Tier 3
            if row_idx < 2:
                sns.scatterplot(
                    data=tier_data,
                    x="flux_date",
                    y=variable,
                    hue="qc_flag",
                    palette="viridis",
                    ax=ax,
                    s=10,
                    alpha=0.6,
                    legend=(row_idx == 0 and col_idx == n_chambers - 1),
                )
            else:
                sns.scatterplot(
                    data=tier_data, x="flux_date", y=variable, color="green", ax=ax, s=10, alpha=0.6
                )

            # Set Titles only on top row or specifically
            tier_count = len(tier_data)
            ax.set_title(f"{chamber} - {tier_name}\nN={tier_count}", fontsize=10)

            # Only set Y label for the first column
            if col_idx == 0:
                ax.set_ylabel("CO2 Flux (umol m-2 s-1)")
            else:
                ax.set_ylabel("")

            if row_idx == 2:
                ax.set_xlabel("Date")

            ax.grid(True, alpha=0.3)

    # Apply unified y-limits per row
    for row_idx in range(3):
        row_min, row_max = tier_limits[row_idx]
        if row_min != float("inf") and row_max != float("-inf"):
            # Add some padding (e.g. 5%)
            margin = (row_max - row_min) * 0.05
            if margin == 0:  # Handle flat case
                margin = 1.0

            for col_idx in range(n_chambers):
                axes[row_idx, col_idx].set_ylim(row_min - margin, row_max + margin)

    fig.suptitle(title, fontsize=16)
    plt.tight_layout()
    return fig


def plot_tropical_seasonal_diurnal(
    flux_df, variable="flux_absolute", estimator="mean", title_suffix=""
):
    """
    Plots diurnal cycles separated by Tropical Seasons (Wet vs Dry).
    Assumptions:
    - Dry Season: May - September
    - Wet Season: October - April
    (Adjust mapping as per user needs if specified, defaulting to standard SE Asia implementation)
    """
    if flux_df.empty:
        return

    df = flux_df.copy()
    df["Month"] = df["flux_date"].dt.month

    # Tropical Season Mapping
    def get_season(month):
        if 5 <= month <= 9:  # May to Sept
            return "Dry Season"
        else:
            return "Wet Season"

    df["Season"] = df["Month"].apply(get_season)
    df["Hour"] = df["flux_date"].dt.hour

    plt.figure(figsize=(12, 7))
    sns.lineplot(
        data=df,
        x="Hour",
        y=variable,
        hue="Season",
        style="Source_Chamber",
        palette={"Dry Season": "orange", "Wet Season": "blue"},
        errorbar="sd",
        estimator=estimator,
    )

    plt.title(f"Diurnal Flux Cycle: Wet vs Dry Season {title_suffix}", fontsize=14)
    plt.xlabel("Hour of Day", fontsize=12)
    plt.ylabel("CO2 Flux (umol m-2 s-1)", fontsize=12)
    plt.xticks(range(0, 25, 2))
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    return plt.gcf()


def plot_flux_heatmap(flux_df, variable="flux_absolute", title="Flux Heatmap (Hour vs Month)"):
    """
    Create heatmaps of Flux values with Hour of Day on Y-axis and Month on X-axis.
    Generates 3 subplots: Overall, Chamber 1, and Chamber 2.
    """
    if flux_df.empty:
        return

    df = flux_df.copy()
    df["Hour"] = df["flux_date"].dt.hour
    df["MonthYear"] = df["flux_date"].dt.to_period("M")

    # helper to plot one heatmap
    def create_pivot_and_plot(data, ax, plot_title):
        if data.empty:
            ax.text(0.5, 0.5, "No Data", ha="center", va="center")
            return

        pivot_df = data.pivot_table(
            index="Hour", columns="MonthYear", values=variable, aggfunc="mean"
        )
        sns.heatmap(
            pivot_df,
            cmap="RdBu_r",
            center=0,
            cbar_kws={"label": "Mean CO2 Flux (umol m-2 s-1)"},
            ax=ax,
        )
        ax.set_title(plot_title, fontsize=12)
        ax.set_xlabel("Month", fontsize=10)
        ax.set_ylabel("Hour of Day", fontsize=10)
        ax.tick_params(axis="y", rotation=0)

    fig, axes = plt.subplots(3, 1, figsize=(15, 24))

    # 1. Overall
    create_pivot_and_plot(df, axes[0], f"{title} - Overall (All Chambers)")

    # 2. Chamber 1
    c1_df = df[df["Source_Chamber"] == "Chamber 1"]
    create_pivot_and_plot(c1_df, axes[1], f"{title} - Chamber 1")

    # 3. Chamber 2
    c2_df = df[df["Source_Chamber"] == "Chamber 2"]
    create_pivot_and_plot(c2_df, axes[2], f"{title} - Chamber 2")

    plt.tight_layout()
    return fig


def plot_flux_vs_tree_age(flux_df, variable="flux_absolute", birth_date_str="2022-07-12"):
    """
    Plots flux against Tree Age in Years. Faceted by Chamber.
    """
    if flux_df.empty:
        return

    birth_date = pd.to_datetime(birth_date_str)

    df = flux_df.copy()
    # Calculate Age in Years
    df["Tree_Age_Years"] = (df["flux_date"] - birth_date).dt.total_seconds() / (3600 * 24 * 365.25)

    chambers = sorted(df["Source_Chamber"].unique())
    n_chambers = len(chambers)
    fig, axes = plt.subplots(nrows=n_chambers, ncols=1, figsize=(14, 4 * n_chambers), sharex=True)
    if n_chambers == 1:
        axes = [axes]

    palette = {"Chamber 1": "#1f77b4", "Chamber 2": "#ff7f0e"}

    for ax, chamber in zip(axes, chambers, strict=False):
        group = df[df["Source_Chamber"] == chamber].sort_values("Tree_Age_Years")
        color = palette.get(chamber, "#1f77b4")

        # Scatter
        sns.scatterplot(
            data=group,
            x="Tree_Age_Years",
            y=variable,
            color=color,
            s=15,
            alpha=0.2,
            linewidth=0,
            ax=ax,
        )

        # Rolling mean for trend
        rolling = group[variable].rolling(window=200, center=True).mean()
        ax.plot(
            group["Tree_Age_Years"], rolling, color="black", label="Trend", linewidth=2, alpha=0.8
        )

        ax.set_title(f"CO2 Flux vs Tree Age: {chamber}", fontsize=12)
        ax.set_ylabel("CO2 Flux (umol m-2 s-1)", fontsize=10)
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Tree Age (Years)", fontsize=12)
    plt.tight_layout()
    return fig


def plot_cumulative_flux_with_gaps(flux_df, gap_filled_df=None, birth_date_str="2024-02-01"):
    """
    Plots cumulative flux with x-axis as Months After Planting (MAP).
    Assumes planting date is 2024-02-01.
    """
    plt.figure(figsize=(15, 6))

    birth_date = pd.to_datetime(birth_date_str)

    if gap_filled_df is not None:
        for chamber, group in gap_filled_df.groupby("Source_Chamber"):
            group = group.sort_index()

            # Calculate MAP
            # (Date - BirthDate) / 30 days approx
            group["MAP"] = (group.index - birth_date).days / 30.44

            cumulative = group["flux_filled"].cumsum()

            plt.plot(group["MAP"], cumulative, label=f"{chamber} (Gap Filled)", linewidth=2)

    plt.title("Cumulative CO2 Flux (Gap-Filled)", fontsize=14)
    plt.ylabel("Cumulative Flux (Arbitrary Units / Sum)", fontsize=12)
    plt.xlabel("Months After Planting (MAP)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    return plt.gcf()


def plot_cumulative_flux_by_date(gap_filled_df):
    """
    Plots cumulative flux with x-axis as Actual Date using the gap-filled hourly data.
    """
    plt.figure(figsize=(15, 6))

    if gap_filled_df is not None:
        for chamber, group in gap_filled_df.groupby("Source_Chamber"):
            group = group.sort_index()

            # Since data is hourly, simple cumsum works as an "Hours * Flux" integration
            # or simply accumulation of the rate per step.
            cumulative = group["flux_filled"].cumsum()

            plt.plot(group.index, cumulative, label=f"{chamber} (Gap Filled)", linewidth=2)

    plt.title("Cumulative CO2 Flux (Gap-Filled) - Actual Date", fontsize=14)
    plt.ylabel("Cumulative Flux (Arbitrary Units)", fontsize=12)
    plt.xlabel("Date", fontsize=12)

    # Format x-axis dates nicely
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    plt.gca().xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    plt.xticks(rotation=45)

    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    return plt.gcf()


def plot_concentration_slope_vs_tree_age(
    flux_df, variable="flux_slope", birth_date_str="2022-07-12"
):
    """
    Plots pure Concentration Slope (ppm/s) against Tree Age in Years. Faceted.
    This excludes the chamber size (Volume/Area) correction.
    """
    if flux_df.empty:
        return

    birth_date = pd.to_datetime(birth_date_str)

    df = flux_df.copy()
    # Calculate Age in Years
    df["Tree_Age_Years"] = (df["flux_date"] - birth_date).dt.total_seconds() / (3600 * 24 * 365.25)

    chambers = sorted(df["Source_Chamber"].unique())
    n_chambers = len(chambers)
    fig, axes = plt.subplots(nrows=n_chambers, ncols=1, figsize=(14, 4 * n_chambers), sharex=True)
    if n_chambers == 1:
        axes = [axes]

    palette = {"Chamber 1": "#1f77b4", "Chamber 2": "#ff7f0e"}

    for ax, chamber in zip(axes, chambers, strict=False):
        group = df[df["Source_Chamber"] == chamber].sort_values("Tree_Age_Years")
        color = palette.get(chamber, "#ff7f0e")

        sns.scatterplot(
            data=group,
            x="Tree_Age_Years",
            y=variable,
            color=color,
            s=15,
            alpha=0.15,
            linewidth=0,
            ax=ax,
        )

        # Rolling mean
        rolling = group[variable].rolling(window=200, center=True).mean()
        ax.plot(
            group["Tree_Age_Years"], rolling, color="black", label="Trend", linewidth=2, alpha=0.8
        )

        ax.set_title(f"Concentration Slope vs Tree Age: {chamber}", fontsize=12)
        ax.set_ylabel("Slope (ppm/s)", fontsize=10)
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Tree Age (Years)", fontsize=12)
    plt.tight_layout()
    return fig


def plot_flux_boxplot_vs_tree_age(
    flux_df, variable="flux_absolute", birth_date_str="2022-07-12", bin_size_days=30
):
    """
    Plots flux boxplots binned by Tree Age (e.g., Monthly).
    """
    if flux_df.empty:
        return

    birth_date = pd.to_datetime(birth_date_str)

    df = flux_df.copy()
    # Calculate Age in Days for binning
    df["Tree_Age_Days"] = (df["flux_date"] - birth_date).dt.days

    # Create Bins (e.g., every 30 days)
    df["Age_Bin"] = (df["Tree_Age_Days"] // bin_size_days) * bin_size_days

    # Convert back to approx years for labelling
    df["Age_Bin_Years"] = df["Age_Bin"] / 365.25

    chambers = sorted(df["Source_Chamber"].unique())
    n_chambers = len(chambers)
    fig, axes = plt.subplots(nrows=n_chambers, ncols=1, figsize=(14, 5 * n_chambers), sharex=True)
    if n_chambers == 1:
        axes = [axes]

    palette = {"Chamber 1": "#1f77b4", "Chamber 2": "#ff7f0e"}

    for ax, chamber in zip(axes, chambers, strict=False):
        group = df[df["Source_Chamber"] == chamber]
        color = palette.get(chamber, "#1f77b4")

        sns.boxplot(data=group, x="Age_Bin_Years", y=variable, color=color, ax=ax, showfliers=False)

        # Adjust x-tick labels to be readable
        ax.set_title(f"CO2 Flux Boxplots (Monthly Bins): {chamber}", fontsize=12)
        ax.set_ylabel("CO2 Flux (umol m-2 s-1)", fontsize=10)
        ax.grid(True, alpha=0.3)

        # Reduce x-tick density if too crowded
        if len(group["Age_Bin_Years"].unique()) > 20:
            for index, label in enumerate(ax.get_xticklabels()):
                if index % 2 != 0:
                    label.set_visible(False)

    axes[-1].set_xlabel("Tree Age (Years)", fontsize=12)
    plt.tight_layout()
    return fig


def plot_concentration_slope_boxplot_vs_tree_age(
    flux_df, variable="flux_slope", birth_date_str="2022-07-12", bin_size_days=30
):
    """
    Plots concentration slope boxplots binned by Tree Age (e.g., Monthly).
    """
    if flux_df.empty:
        return

    birth_date = pd.to_datetime(birth_date_str)

    df = flux_df.copy()
    df["Tree_Age_Days"] = (df["flux_date"] - birth_date).dt.days
    df["Age_Bin"] = (df["Tree_Age_Days"] // bin_size_days) * bin_size_days
    df["Age_Bin_Years"] = df["Age_Bin"] / 365.25

    chambers = sorted(df["Source_Chamber"].unique())
    n_chambers = len(chambers)
    fig, axes = plt.subplots(nrows=n_chambers, ncols=1, figsize=(14, 5 * n_chambers), sharex=True)
    if n_chambers == 1:
        axes = [axes]

    palette = {"Chamber 1": "#1f77b4", "Chamber 2": "#ff7f0e"}

    for ax, chamber in zip(axes, chambers, strict=False):
        group = df[df["Source_Chamber"] == chamber]
        color = palette.get(chamber, "#ff7f0e")

        sns.boxplot(data=group, x="Age_Bin_Years", y=variable, color=color, ax=ax, showfliers=False)

        ax.set_title(f"Concentration Slope Boxplots (Monthly Bins): {chamber}", fontsize=12)
        ax.set_ylabel("Slope (ppm/s)", fontsize=10)
        ax.grid(True, alpha=0.3)

        if len(group["Age_Bin_Years"].unique()) > 20:
            for index, label in enumerate(ax.get_xticklabels()):
                if index % 2 != 0:
                    label.set_visible(False)

    axes[-1].set_xlabel("Tree Age (Years)", fontsize=12)
    plt.tight_layout()
    return fig


def plot_flux_monthly_boxplot(flux_df, variable="flux_absolute"):
    """
    Plots flux distribution binned by Month-Year (Timeseries Boxplot).
    Faceted by Chamber.
    """
    if flux_df.empty:
        return

    df = flux_df.copy()
    # Create Month-Year column for sorting/plotting
    # We sort by date first to ensure labels are chronological
    df = df.sort_values("flux_date")
    df["MonthYear"] = df["flux_date"].dt.to_period("M").astype(str)

    # Sort MonthYear to ensure chronological order for the x-axis
    month_order = sorted(df["MonthYear"].unique())

    chambers = sorted(df["Source_Chamber"].unique())
    n_chambers = len(chambers)

    # Share X axis to align time series
    fig, axes = plt.subplots(n_chambers, 1, figsize=(14, 5 * n_chambers), sharex=True, sharey=True)
    if n_chambers == 1:
        axes = [axes]

    palette = {"Chamber 1": "#1f77b4", "Chamber 2": "#ff7f0e"}

    for ax, chamber in zip(axes, chambers, strict=False):
        group = df[df["Source_Chamber"] == chamber]
        color = palette.get(chamber, "#1f77b4")

        if group.empty:
            continue

        # Use 'order' to ensure all months are present and aligned across subplots
        sns.boxplot(
            data=group,
            x="MonthYear",
            y=variable,
            color=color,
            ax=ax,
            showfliers=False,
            order=month_order,
        )

        ax.set_title(f"Monthly CO2 Flux Distribution: {chamber}", fontsize=12)
        ax.set_ylabel("CO2 Flux (umol m-2 s-1)", fontsize=10)
        ax.grid(True, alpha=0.3)

        # Rotate x-labels for better readability
        ax.tick_params(axis="x", rotation=45)

    axes[-1].set_xlabel("Month-Year", fontsize=12)
    plt.tight_layout()
    return fig
