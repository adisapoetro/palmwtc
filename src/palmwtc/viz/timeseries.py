"""Time-series and seasonal-pattern plots for chamber flux data.

Plots for visualising how CO2 and H2O fluxes vary with time of day, day
of year, and tree age:

- :func:`plot_flux_timeseries_tiers` -- scatter timeseries faceted by QC
  tier and chamber, useful for a quick data-quality overview.
- :func:`plot_tropical_seasonal_diurnal` -- overlay diurnal pattern per
  tropical season (Wet vs Dry) on a single axis.
- :func:`plot_flux_heatmap` -- hour-of-day x month heatmap (3 subplots:
  overall, Chamber 1, Chamber 2).
- :func:`plot_flux_vs_tree_age` -- flux trend across palm-age cohorts,
  with rolling mean, faceted by chamber.
- :func:`plot_cumulative_flux_with_gaps` -- cumulative gap-filled flux
  plotted against months after planting (MAP).
- :func:`plot_cumulative_flux_by_date` -- cumulative gap-filled flux
  plotted against actual calendar date.
- :func:`plot_concentration_slope_vs_tree_age` -- raw concentration slope
  (ppm/s, no chamber-size correction) vs tree age.
- :func:`plot_flux_boxplot_vs_tree_age` -- monthly-binned flux boxplots
  vs tree age.
- :func:`plot_concentration_slope_boxplot_vs_tree_age` -- monthly-binned
  concentration-slope boxplots vs tree age.
- :func:`plot_flux_monthly_boxplot` -- month-year boxplots faceted by
  chamber.

All functions return a :class:`matplotlib.figure.Figure` (or ``None``
when the input DataFrame is empty).
"""

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def plot_flux_timeseries_tiers(
    flux_df: pd.DataFrame,
    variable: str = "flux_absolute",
    title: str = "CO2 Flux Timeseries by QC Tier",
) -> "plt.Figure | None":
    """Plot flux timeseries split into three QC-quality tiers.

    Produces a grid of scatter plots: rows are QC tiers (Tier 1 = all
    data, Tier 2 = flags 0+1, Tier 3 = flag 0 only), columns are
    chambers. Points in Tiers 1 and 2 are coloured by ``qc_flag``
    (viridis palette); Tier-3 points are green.

    Parameters
    ----------
    flux_df : pd.DataFrame
        Cycle-level flux data. Must contain:

        ``Source_Chamber`` : str
            Chamber identifier (e.g. ``"Chamber 1"``).
        ``flux_date`` : datetime-like
            Timestamp of each measurement cycle.
        ``qc_flag`` : int
            QC flag (0 = high quality, 1 = medium, 2 = low).
        ``<variable>`` : float
            Flux column to plot on the y-axis.
    variable : str, optional
        Column in ``flux_df`` to use as the y-axis value.
        Default is ``"flux_absolute"``.
    title : str, optional
        Overall figure title. Default is
        ``"CO2 Flux Timeseries by QC Tier"``.

    Returns
    -------
    matplotlib.figure.Figure or None
        The figure containing the 3-row x N-chamber grid, or ``None``
        if ``flux_df`` is empty.

    Notes
    -----
    Y-axis limits are unified per row so comparisons between chambers
    within the same tier are on the same scale. Each row's limits are
    derived from all chambers in that row, with 5 % padding.

    Examples
    --------
    >>> from palmwtc.viz.timeseries import plot_flux_timeseries_tiers
    >>> fig = plot_flux_timeseries_tiers(cycles_df)  # doctest: +SKIP
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
    flux_df: pd.DataFrame,
    variable: str = "flux_absolute",
    estimator: str = "mean",
    title_suffix: str = "",
) -> "plt.Figure | None":
    """Overlay diurnal flux pattern per tropical season on a single axis.

    Draws one line per season (Wet and Dry) and per chamber. The x-axis
    is hour of day (0-23), the y-axis is the flux value aggregated
    across all dates in that season-hour combination.

    Season assignment follows the standard SE-Asia rule:

    - **Dry Season**: May to September (months 5-9).
    - **Wet Season**: October to April (months 10-4).

    Useful for spotting shifts in CO2 uptake phase (morning vs afternoon
    activity) between seasons.

    Parameters
    ----------
    flux_df : pd.DataFrame
        Cycle-level flux data. Must contain:

        ``flux_date`` : datetime-like
            Timestamp of each measurement cycle; month and hour are
            extracted from this column.
        ``Source_Chamber`` : str
            Chamber identifier used to differentiate line styles.
        ``<variable>`` : float
            Flux column plotted on the y-axis.
    variable : str, optional
        Column in ``flux_df`` to use as the y-axis value.
        Default is ``"flux_absolute"``.
    estimator : str, optional
        Aggregation function passed to ``seaborn.lineplot``
        (e.g. ``"mean"``, ``"median"``). Default is ``"mean"``.
    title_suffix : str, optional
        Extra text appended to the figure title, useful for adding
        a date range or site label. Default is ``""``.

    Returns
    -------
    matplotlib.figure.Figure or None
        The figure containing the diurnal plot, or ``None`` if
        ``flux_df`` is empty.

    Notes
    -----
    Shaded bands around each line represent one standard deviation
    (``errorbar="sd"``). Lines are coloured orange (Dry) and blue (Wet);
    line style differentiates chambers.

    Examples
    --------
    >>> from palmwtc.viz.timeseries import plot_tropical_seasonal_diurnal
    >>> fig = plot_tropical_seasonal_diurnal(cycles_df)  # doctest: +SKIP
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


def plot_flux_heatmap(
    flux_df: pd.DataFrame,
    variable: str = "flux_absolute",
    title: str = "Flux Heatmap (Hour vs Month)",
) -> "plt.Figure | None":
    """Heatmap of mean flux by hour-of-day and month-year.

    Produces three vertically stacked subplots:

    1. Overall (all chambers combined).
    2. Chamber 1 only.
    3. Chamber 2 only.

    Each subplot has hour of day (0-23) on the y-axis and month-year
    periods on the x-axis. Cell colour encodes mean flux, centred at
    zero (``RdBu_r`` palette: red = positive efflux, blue = uptake).

    Parameters
    ----------
    flux_df : pd.DataFrame
        Cycle-level flux data. Must contain:

        ``flux_date`` : datetime-like
            Timestamp; hour and month-year are extracted from this column.
        ``Source_Chamber`` : str
            Chamber identifier. Subplots 2 and 3 filter on
            ``"Chamber 1"`` and ``"Chamber 2"`` exactly.
        ``<variable>`` : float
            Flux column used for heatmap cell values.
    variable : str, optional
        Column in ``flux_df`` to aggregate. Default is
        ``"flux_absolute"``.
    title : str, optional
        Base title; each subplot appends its own suffix
        (e.g. ``"- Chamber 1"``). Default is
        ``"Flux Heatmap (Hour vs Month)"``.

    Returns
    -------
    matplotlib.figure.Figure or None
        The figure with three heatmap subplots, or ``None`` if
        ``flux_df`` is empty.

    Notes
    -----
    Subplots where the filtered data is empty show a ``"No Data"``
    label instead of a heatmap. Month-year periods on the x-axis
    are sorted chronologically by pandas ``Period`` ordering.

    Examples
    --------
    >>> from palmwtc.viz.timeseries import plot_flux_heatmap
    >>> fig = plot_flux_heatmap(cycles_df)  # doctest: +SKIP
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


def plot_flux_vs_tree_age(
    flux_df: pd.DataFrame,
    variable: str = "flux_absolute",
    birth_date_str: str = "2022-07-12",
) -> "plt.Figure | None":
    """Plot flux against tree age in years, with a rolling-mean trend.

    Produces one subplot per chamber (stacked vertically, shared x-axis).
    Each subplot shows raw flux values as a semi-transparent scatter and
    a black rolling-mean line (window = 200 observations) as the trend.

    Parameters
    ----------
    flux_df : pd.DataFrame
        Cycle-level flux data. Must contain:

        ``flux_date`` : datetime-like
            Timestamp of each measurement cycle; used to compute tree
            age relative to ``birth_date_str``.
        ``Source_Chamber`` : str
            Chamber identifier; one subplot is created per unique value.
        ``<variable>`` : float
            Flux column plotted on the y-axis.
    variable : str, optional
        Column in ``flux_df`` to plot. Default is ``"flux_absolute"``.
    birth_date_str : str, optional
        ISO-format planting date (``"YYYY-MM-DD"``) used as the zero
        point for tree age. Default is ``"2022-07-12"``.

    Returns
    -------
    matplotlib.figure.Figure or None
        The figure with one subplot per chamber, or ``None`` if
        ``flux_df`` is empty.

    Notes
    -----
    Tree age in years is computed as::

        (flux_date - birth_date).total_seconds() / (3600 * 24 * 365.25)

    so fractional years are preserved. The rolling mean uses
    ``window=200, center=True`` and will produce NaN near the edges of
    the series; those NaN values are silently dropped by matplotlib.

    Examples
    --------
    >>> from palmwtc.viz.timeseries import plot_flux_vs_tree_age
    >>> fig = plot_flux_vs_tree_age(cycles_df, birth_date_str="2022-07-12")  # doctest: +SKIP
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


def plot_cumulative_flux_with_gaps(
    flux_df: pd.DataFrame,
    gap_filled_df: "pd.DataFrame | None" = None,
    birth_date_str: str = "2024-02-01",
) -> "plt.Figure":
    """Plot cumulative gap-filled flux vs months after planting (MAP).

    Draws one line per chamber from the gap-filled hourly data.
    The x-axis is months after planting (MAP), computed as::

        (index - birth_date).days / 30.44

    The y-axis is the running cumulative sum of ``flux_filled``.

    Parameters
    ----------
    flux_df : pd.DataFrame
        Cycle-level flux data. Not used directly in the current
        implementation; kept for API symmetry with related functions.
    gap_filled_df : pd.DataFrame or None, optional
        Hourly gap-filled data with a datetime index. Must contain:

        ``Source_Chamber`` : str
            Chamber identifier; one line per unique value.
        ``flux_filled`` : float
            Gap-filled flux values to accumulate.
        ``index`` : datetime-like
            Row index used to compute elapsed time since planting.
    birth_date_str : str, optional
        ISO-format planting date (``"YYYY-MM-DD"``) used as the MAP
        zero point. Default is ``"2024-02-01"``.

    Returns
    -------
    matplotlib.figure.Figure
        The figure with the cumulative flux curves. Returns an empty
        figure if ``gap_filled_df`` is ``None``.

    Notes
    -----
    MAP is an approximate unit: one month is assumed to be 30.44 days.
    The y-axis is labelled "Cumulative Flux (Arbitrary Units / Sum)"
    because the cumulative sum of a flux *rate* is not a standard
    physical quantity without explicit time-step integration.

    Examples
    --------
    >>> from palmwtc.viz.timeseries import plot_cumulative_flux_with_gaps
    >>> fig = plot_cumulative_flux_with_gaps(cycles_df, gap_filled_df=hourly_df)  # doctest: +SKIP
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


def plot_cumulative_flux_by_date(
    gap_filled_df: "pd.DataFrame | None",
) -> "plt.Figure":
    """Plot cumulative gap-filled flux against actual calendar date.

    Draws one line per chamber. The x-axis is the datetime index of
    ``gap_filled_df``; the y-axis is the running cumulative sum of
    ``flux_filled``. Useful for comparing absolute accumulation across
    chambers on a shared calendar timeline.

    Parameters
    ----------
    gap_filled_df : pd.DataFrame or None
        Hourly gap-filled data with a datetime index. Must contain:

        ``Source_Chamber`` : str
            Chamber identifier; one line per unique value.
        ``flux_filled`` : float
            Gap-filled flux values to accumulate.
        ``index`` : datetime-like
            Row index used as the x-axis.

    Returns
    -------
    matplotlib.figure.Figure
        The figure with the cumulative flux curves. Returns an empty
        figure if ``gap_filled_df`` is ``None``.

    Notes
    -----
    The x-axis is formatted with monthly ticks and
    ``"%Y-%m-%d"`` date labels, rotated 45 degrees for readability.

    Examples
    --------
    >>> from palmwtc.viz.timeseries import plot_cumulative_flux_by_date
    >>> fig = plot_cumulative_flux_by_date(hourly_df)  # doctest: +SKIP
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
    flux_df: pd.DataFrame,
    variable: str = "flux_slope",
    birth_date_str: str = "2022-07-12",
) -> "plt.Figure | None":
    """Plot raw concentration slope vs tree age, faceted by chamber.

    Plots ppm/s slope (before chamber volume/area correction) against
    tree age in years. Produces one subplot per chamber with a scatter
    layer and a black rolling-mean trend line. This is a sanity check
    for :func:`plot_flux_vs_tree_age`: if the corrected-flux trend
    matches the raw-slope trend, the chamber-size correction is not
    introducing artefacts.

    Parameters
    ----------
    flux_df : pd.DataFrame
        Cycle-level flux data. Must contain:

        ``flux_date`` : datetime-like
            Timestamp of each cycle; used to compute tree age.
        ``Source_Chamber`` : str
            Chamber identifier; one subplot per unique value.
        ``<variable>`` : float
            Raw concentration slope in ppm/s (no chamber-size
            correction applied).
    variable : str, optional
        Column in ``flux_df`` to plot on the y-axis.
        Default is ``"flux_slope"``.
    birth_date_str : str, optional
        ISO-format planting date (``"YYYY-MM-DD"``) for tree-age
        calculation. Default is ``"2022-07-12"``.

    Returns
    -------
    matplotlib.figure.Figure or None
        The figure with one subplot per chamber, or ``None`` if
        ``flux_df`` is empty.

    Notes
    -----
    Tree age is computed the same way as in
    :func:`plot_flux_vs_tree_age` (seconds / 31,557,600). The rolling
    mean uses ``window=200, center=True``.

    Examples
    --------
    >>> from palmwtc.viz.timeseries import plot_concentration_slope_vs_tree_age
    >>> fig = plot_concentration_slope_vs_tree_age(cycles_df)  # doctest: +SKIP
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
    flux_df: pd.DataFrame,
    variable: str = "flux_absolute",
    birth_date_str: str = "2022-07-12",
    bin_size_days: int = 30,
) -> "plt.Figure | None":
    """Boxplots of flux binned by tree age, one subplot per chamber.

    Groups measurement cycles into equal-width bins of
    ``bin_size_days`` days and draws a boxplot per bin. The x-axis
    label shows approximate tree age in years for each bin. Outliers
    are hidden (``showfliers=False``).

    Parameters
    ----------
    flux_df : pd.DataFrame
        Cycle-level flux data. Must contain:

        ``flux_date`` : datetime-like
            Timestamp used to compute age relative to ``birth_date_str``.
        ``Source_Chamber`` : str
            Chamber identifier; one subplot per unique value.
        ``<variable>`` : float
            Flux column used for the boxplot values.
    variable : str, optional
        Column in ``flux_df`` to plot. Default is ``"flux_absolute"``.
    birth_date_str : str, optional
        ISO-format planting date (``"YYYY-MM-DD"``) for tree-age
        calculation. Default is ``"2022-07-12"``.
    bin_size_days : int, optional
        Width of each age bin in days. Default is ``30`` (roughly
        one month).

    Returns
    -------
    matplotlib.figure.Figure or None
        The figure with one subplot per chamber, or ``None`` if
        ``flux_df`` is empty.

    Notes
    -----
    When there are more than 20 unique bins on the x-axis, every other
    tick label is hidden to prevent overplotting. Subplots share the
    x-axis so bin positions are aligned across chambers.

    Examples
    --------
    >>> from palmwtc.viz.timeseries import plot_flux_boxplot_vs_tree_age
    >>> fig = plot_flux_boxplot_vs_tree_age(cycles_df, bin_size_days=30)  # doctest: +SKIP
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
    flux_df: pd.DataFrame,
    variable: str = "flux_slope",
    birth_date_str: str = "2022-07-12",
    bin_size_days: int = 30,
) -> "plt.Figure | None":
    """Boxplots of concentration slope binned by tree age, per chamber.

    Companion to :func:`plot_flux_boxplot_vs_tree_age` but for the raw
    concentration slope (ppm/s, no chamber-size correction). Useful for
    checking whether trends in the corrected flux are driven by real
    biological change or by chamber resizing events.

    Parameters
    ----------
    flux_df : pd.DataFrame
        Cycle-level flux data. Must contain:

        ``flux_date`` : datetime-like
            Timestamp used to compute age relative to ``birth_date_str``.
        ``Source_Chamber`` : str
            Chamber identifier; one subplot per unique value.
        ``<variable>`` : float
            Raw concentration slope in ppm/s.
    variable : str, optional
        Column in ``flux_df`` to plot. Default is ``"flux_slope"``.
    birth_date_str : str, optional
        ISO-format planting date (``"YYYY-MM-DD"``) for tree-age
        calculation. Default is ``"2022-07-12"``.
    bin_size_days : int, optional
        Width of each age bin in days. Default is ``30``.

    Returns
    -------
    matplotlib.figure.Figure or None
        The figure with one subplot per chamber, or ``None`` if
        ``flux_df`` is empty.

    Notes
    -----
    Outliers are hidden (``showfliers=False``). When there are more than
    20 unique bins, every other x-tick label is hidden. Subplots share
    the x-axis.

    Examples
    --------
    >>> from palmwtc.viz.timeseries import plot_concentration_slope_boxplot_vs_tree_age
    >>> fig = plot_concentration_slope_boxplot_vs_tree_age(cycles_df)  # doctest: +SKIP
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


def plot_flux_monthly_boxplot(
    flux_df: pd.DataFrame,
    variable: str = "flux_absolute",
) -> "plt.Figure | None":
    """Month-year boxplot of flux distribution, faceted by chamber.

    Draws one subplot per chamber (stacked vertically, shared x and
    y axes). Each box represents the distribution of flux values within
    one calendar month. Month-year labels on the x-axis are sorted
    chronologically. Outliers are hidden (``showfliers=False``).

    Parameters
    ----------
    flux_df : pd.DataFrame
        Cycle-level flux data. Must contain:

        ``flux_date`` : datetime-like
            Timestamp; month-year is derived from this column.
        ``Source_Chamber`` : str
            Chamber identifier; one subplot per unique value.
        ``<variable>`` : float
            Flux column used for the boxplot values.
    variable : str, optional
        Column in ``flux_df`` to plot. Default is ``"flux_absolute"``.

    Returns
    -------
    matplotlib.figure.Figure or None
        The figure with one subplot per chamber, or ``None`` if
        ``flux_df`` is empty.

    Notes
    -----
    The ``order`` parameter is passed to ``seaborn.boxplot`` to ensure
    all subplots share the same x-axis ordering even if one chamber is
    missing data for some months. X-tick labels are rotated 45 degrees.

    Examples
    --------
    >>> from palmwtc.viz.timeseries import plot_flux_monthly_boxplot
    >>> fig = plot_flux_monthly_boxplot(cycles_df)  # doctest: +SKIP
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
