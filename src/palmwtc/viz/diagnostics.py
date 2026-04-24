"""Cycle-level diagnostic plots for chamber flux QC review.

Provides functions to inspect individual measurement cycles from the
whole-tree chamber flux pipeline.  Each function creates a matplotlib
figure showing CO₂ concentration traces, regression fits, and residuals
so that flux quality can be reviewed visually.

Public functions
----------------
:func:`plot_chamber_resizing_validation`
    Time-series scatter around the chamber resizing event with a
    rolling-mean trend and a vertical marker at the resize date.
:func:`plot_cycle_diagnostics`
    Fit + residual panels for a single cycle, with optional WPL
    correction labelling.
:func:`plot_specific_cycle`
    Locate a cycle by chamber name and datetime string, then call
    :func:`plot_cycle_diagnostics`.
:func:`plot_cycle_by_id`
    Locate a cycle by chamber name and integer cycle ID, then call
    :func:`plot_cycle_diagnostics`.
:func:`show_sample_cycles`
    Draw ``n`` random cycles from a QC tier and plot each one.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def plot_chamber_resizing_validation(
    flux_df: pd.DataFrame,
    resize_date: str = "2025-07-01",
    variable: str = "flux_absolute",
) -> "plt.Figure | None":
    """Plot the flux signal in a ±60-day window around the chamber resizing date.

    Creates one subplot per chamber (stacked vertically) showing the chosen
    flux variable as a scatter plot, a 50-point centred rolling-mean trend
    line, and a vertical dashed line marking the resize date.  Use this to
    check for artefacts (step changes, drift) introduced by the physical
    chamber adjustment.

    Parameters
    ----------
    flux_df : pandas.DataFrame
        Flux results table.  Must contain columns:

        - ``flux_date`` (datetime64) — timestamp of each flux cycle.
        - ``Source_Chamber`` (str) — chamber identifier
          (e.g. ``"Chamber 1"``).
        - ``<variable>`` (float) — the flux column to plot.

    resize_date : str, default ``"2025-07-01"``
        ISO-format date string for the chamber resizing event.  Passed to
        :func:`pandas.to_datetime`.
    variable : str, default ``"flux_absolute"``
        Name of the column in *flux_df* to plot on the y-axis.

    Returns
    -------
    matplotlib.figure.Figure or None
        The figure object, or ``None`` if *flux_df* is empty or no data
        falls within the ±60-day window.

    Notes
    -----
    The rolling trend uses a window of 50 cycles centred on each point.
    This smooths noise without over-fitting at the edges of the window.

    Examples
    --------
    >>> from palmwtc.viz.diagnostics import plot_chamber_resizing_validation
    >>> fig = plot_chamber_resizing_validation(flux_df, resize_date="2025-07-01")  # doctest: +SKIP
    """
    if flux_df.empty:
        return

    resize_dt = pd.to_datetime(resize_date)

    # Filter data to +/- 60 days around resize
    start_window = resize_dt - pd.Timedelta(days=60)
    end_window = resize_dt + pd.Timedelta(days=60)

    df_window = flux_df[
        (flux_df["flux_date"] >= start_window) & (flux_df["flux_date"] <= end_window)
    ].copy()

    if df_window.empty:
        print("No data found around resizing date.")
        return None

    chambers = sorted(df_window["Source_Chamber"].unique())
    n_chambers = len(chambers)
    fig, axes = plt.subplots(nrows=n_chambers, ncols=1, figsize=(14, 4 * n_chambers), sharex=True)
    if n_chambers == 1:
        axes = [axes]

    palette = {"Chamber 1": "#1f77b4", "Chamber 2": "#ff7f0e"}

    for ax, chamber in zip(axes, chambers, strict=False):
        group = df_window[df_window["Source_Chamber"] == chamber].sort_values("flux_date")
        color = palette.get(chamber, "#1f77b4")

        # Scatter
        sns.scatterplot(
            data=group, x="flux_date", y=variable, color=color, s=15, alpha=0.3, linewidth=0, ax=ax
        )

        # Trend
        rolling = group[variable].rolling(window=50, center=True).mean()
        ax.plot(group["flux_date"], rolling, color="black", linewidth=2, alpha=0.8, label="Trend")

        # Vertical line
        ax.axvline(resize_dt, color="red", linestyle="--", linewidth=2, label="Resize")

        ax.set_title(f"Chamber Resizing Validation: {chamber}", fontsize=12)
        ax.set_ylabel("CO2 Flux (umol m-2 s-1)", fontsize=10)
        ax.legend()
        ax.grid(True)

    axes[-1].set_xlabel("Date", fontsize=12)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Cycle Diagnostic Plots
# ---------------------------------------------------------------------------


def plot_cycle_diagnostics(
    raw_df: pd.DataFrame,
    flux_row: pd.Series,
    apply_wpl: bool = False,
) -> None:
    """Plot a single flux cycle with its fit line, residuals, and QC metadata.

    Produces a 1x2 figure:

    - **Left panel** — CO₂ concentration vs. time.  Shows the raw wet CO₂
      signal (gray, if available), the dry (or WPL-corrected) CO₂ used for
      fitting (blue), the fitting window subset (orange), and the regression
      fit line (red dashed).
    - **Right panel** — Residuals of the fit within the fitting window.

    After displaying the figure, prints the QC reason string and, when
    *apply_wpl* is ``True`` and ``wpl_delta_ppm`` is present in *raw_df*,
    also prints the median WPL delta and 95th-percentile relative change.

    Parameters
    ----------
    raw_df : pandas.DataFrame
        Raw chamber time-series.  Must contain columns:

        - ``TIMESTAMP`` (datetime64) — measurement time.
        - ``CO2`` (float) — dry (or WPL-corrected) CO₂ concentration (ppm).
        - ``CO2_raw`` (float, optional) — uncorrected wet CO₂ concentration
          (ppm).  Plotted in gray if present.
        - ``wpl_delta_ppm`` (float, optional) — WPL correction magnitude.
          Printed if *apply_wpl* is ``True``.
        - ``wpl_rel_change`` (float, optional) — relative WPL change.
          Printed if *apply_wpl* is ``True``.

    flux_row : pandas.Series
        Single row from a flux results DataFrame.  Must contain:

        - ``flux_date`` (datetime64) — cycle start time.
        - ``cycle_duration_sec`` (float) — cycle length in seconds.
        - ``window_start_sec`` (float) — fit window start offset (s).
        - ``window_end_sec`` (float) — fit window end offset (s).
        - ``flux_slope`` (float) — regression slope (ppm s⁻¹).
        - ``flux_intercept`` (float) — regression intercept (ppm).
        - ``flux_qc_label`` (str) — QC tier label.
        - ``cycle_id`` (int or float) — unique cycle identifier.
        - ``Source_Chamber`` (str) — chamber name.
        - ``qc_reason`` (str, optional) — human-readable QC reason.

    apply_wpl : bool, default False
        If ``True``, label the CO₂ trace as WPL-corrected and print WPL
        summary statistics after the plot.

    Returns
    -------
    None
        Displays the figure inline (calls :func:`matplotlib.pyplot.show`)
        and prints QC metadata to stdout.  Does not return the figure object.

    Notes
    -----
    The function returns early (prints a message, no figure) if no raw data
    falls within the cycle window, or if the fitting window subset is empty.

    Examples
    --------
    >>> from palmwtc.viz.diagnostics import plot_cycle_diagnostics
    >>> plot_cycle_diagnostics(raw_df, flux_row)  # doctest: +SKIP
    """
    import matplotlib.pyplot as plt

    start = flux_row["flux_date"]
    end = start + pd.Timedelta(seconds=flux_row["cycle_duration_sec"] + 5)

    cycle_data = raw_df[(raw_df["TIMESTAMP"] >= start) & (raw_df["TIMESTAMP"] <= end)]
    if cycle_data.empty:
        print("No raw data found for this cycle.")
        return

    t = (cycle_data["TIMESTAMP"] - cycle_data["TIMESTAMP"].min()).dt.total_seconds().values
    y = cycle_data["CO2"].values
    y_raw = cycle_data["CO2_raw"].values if "CO2_raw" in cycle_data.columns else None

    mask = (t >= flux_row["window_start_sec"]) & (t <= flux_row["window_end_sec"])
    t_fit = t[mask]

    if len(t_fit) == 0:
        print("No window data for this cycle.")
        return

    y_fit = flux_row["flux_slope"] * t_fit + flux_row["flux_intercept"]

    _fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    if y_raw is not None:
        axes[0].scatter(t, y_raw, s=8, alpha=0.25, color="gray", label="Wet CO2 (raw)")
    co2_label = "Dry CO2 (WPL)" if apply_wpl else "CO2 used for flux"
    axes[0].scatter(t, y, s=10, alpha=0.45, label=co2_label)
    axes[0].scatter(t_fit, y[mask], s=12, color="orange", label="Used window")
    axes[0].plot(t_fit, y_fit, color="red", linestyle="--", label="Fit")
    axes[0].set_title(
        f"{flux_row['Source_Chamber']} cycle {int(flux_row['cycle_id'])} "
        f"| QC {flux_row['flux_qc_label']}"
    )
    axes[0].set_xlabel("Seconds")
    axes[0].set_ylabel("CO2 (ppm, dry)" if apply_wpl else "CO2 (ppm)")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    resid = y[mask] - y_fit
    axes[1].scatter(t_fit, resid, s=10, alpha=0.6)
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_title("Residuals")
    axes[1].set_xlabel("Seconds")
    axes[1].set_ylabel("CO2 residual (ppm)")
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()

    reason_text = flux_row.get("qc_reason", "").strip() or "none"
    print(f"QC reason: {reason_text}")

    if apply_wpl and "wpl_delta_ppm" in cycle_data.columns:
        delta = cycle_data["wpl_delta_ppm"].dropna()
        rel = cycle_data.get("wpl_rel_change", pd.Series(dtype=float)).abs().dropna()
        if not delta.empty:
            msg = f"WPL median delta: {delta.median():.3f} ppm"
            if not rel.empty:
                msg += f" | p95|rel|: {np.percentile(rel, 95):.4f}"
            print(msg)


def plot_specific_cycle(
    data: pd.DataFrame,
    raw_lookup: dict,
    chamber: str,
    date_str: str,
    apply_wpl: bool = False,
) -> None:
    """Plot diagnostics for a cycle identified by chamber name and datetime string.

    Finds the cycle in *data* whose ``flux_date`` is closest to *date_str*
    (within 2 seconds), then delegates to :func:`plot_cycle_diagnostics`.

    Parameters
    ----------
    data : pandas.DataFrame
        Flux results table.  Must contain ``Source_Chamber`` (str) and
        ``flux_date`` (datetime64) columns.
    raw_lookup : dict[str, pandas.DataFrame]
        Mapping from chamber name to the corresponding raw time-series
        DataFrame.  Same structure as the *raw_df* argument of
        :func:`plot_cycle_diagnostics`.
    chamber : str
        Chamber name to filter on (e.g. ``"Chamber 1"``).
    date_str : str
        Target datetime in ``"DD/MM/YY HH:MM:SS"`` format (day-first).
    apply_wpl : bool, default False
        Forwarded to :func:`plot_cycle_diagnostics`.

    Returns
    -------
    None
        Calls :func:`plot_cycle_diagnostics` and returns nothing.  Prints
        an informative message if the cycle or raw data cannot be found.

    Notes
    -----
    The 2-second tolerance on ``flux_date`` matching covers the rounding
    that may occur when timestamps are stored at 1 Hz resolution.

    Examples
    --------
    >>> from palmwtc.viz.diagnostics import plot_specific_cycle
    >>> plot_specific_cycle(data, raw_lookup, "Chamber 1", "01/07/25 08:30:00")  # doctest: +SKIP
    """
    try:
        target_dt = pd.to_datetime(date_str, dayfirst=True)
    except Exception as e:
        print(f"Error parsing date '{date_str}': {e}")
        return

    subset = data[data["Source_Chamber"] == chamber]
    if subset.empty:
        print(f"No cycles found for {chamber}")
        return

    subset = subset.copy()
    subset["_dt_diff"] = (subset["flux_date"] - target_dt).abs()
    best_idx = subset["_dt_diff"].idxmin()
    best_row = subset.loc[best_idx]
    diff = best_row["_dt_diff"]

    if diff > pd.Timedelta(seconds=2):
        print(f"No cycle found matching {date_str} for {chamber}.")
        print(f"Closest available: {best_row['flux_date']} (diff: {diff})")
        return

    print(f"Found cycle: {chamber} @ {best_row['flux_date']}")

    raw_df = raw_lookup.get(chamber)
    if raw_df is None:
        print(f"No raw data loaded for {chamber}")
        return

    plot_cycle_diagnostics(raw_df, best_row, apply_wpl=apply_wpl)


def plot_cycle_by_id(
    data: pd.DataFrame,
    raw_lookup: dict,
    chamber: str,
    cycle_id: int | float,
    apply_wpl: bool = False,
) -> None:
    """Plot diagnostics for a cycle identified by chamber name and cycle ID.

    Finds the row in *data* matching *chamber* and *cycle_id*, then
    delegates to :func:`plot_cycle_diagnostics`.

    Parameters
    ----------
    data : pandas.DataFrame
        Flux results table.  Must contain ``Source_Chamber`` (str) and
        ``cycle_id`` (int or float) columns.
    raw_lookup : dict[str, pandas.DataFrame]
        Mapping from chamber name to raw time-series DataFrame.
    chamber : str
        Chamber name (e.g. ``"Chamber 1"``).
    cycle_id : int or float
        Numeric cycle identifier.  Compared with
        :func:`numpy.isclose` to handle floating-point IDs.
    apply_wpl : bool, default False
        Forwarded to :func:`plot_cycle_diagnostics`.

    Returns
    -------
    None
        Calls :func:`plot_cycle_diagnostics` and returns nothing.  Prints
        an informative message if the cycle or raw data cannot be found.

    Examples
    --------
    >>> from palmwtc.viz.diagnostics import plot_cycle_by_id
    >>> plot_cycle_by_id(data, raw_lookup, "Chamber 1", cycle_id=1042)  # doctest: +SKIP
    """
    subset = data[(data["Source_Chamber"] == chamber) & (np.isclose(data["cycle_id"], cycle_id))]

    if subset.empty:
        print(f"No cycle found for {chamber} with ID {cycle_id}")
        return

    row = subset.iloc[0]
    print(f"Found cycle: {chamber} ID {cycle_id} @ {row['flux_date']}")

    raw_df = raw_lookup.get(chamber)
    if raw_df is None:
        print(f"No raw data loaded for {chamber}")
        return

    plot_cycle_diagnostics(raw_df, row, apply_wpl=apply_wpl)


def show_sample_cycles(
    data: pd.DataFrame,
    raw_lookup: dict,
    tier: int | str,
    n: int = 5,
    seed: int = 42,
    label: str | None = None,
    apply_wpl: bool = False,
) -> None:
    """Plot a random sample of cycles from a given QC tier.

    Randomly draws up to *n* cycles from the rows where ``flux_qc == tier``
    and calls :func:`plot_cycle_diagnostics` for each one.

    Parameters
    ----------
    data : pandas.DataFrame
        Flux results table.  Must contain ``flux_qc`` (int or str) and
        ``Source_Chamber`` (str) columns, plus all columns required by
        :func:`plot_cycle_diagnostics`.
    raw_lookup : dict[str, pandas.DataFrame]
        Mapping from chamber name to raw time-series DataFrame.
    tier : int or str
        QC tier value to filter on (e.g. ``1``, ``2``, ``"HQ"``).
    n : int, default 5
        Maximum number of cycles to plot.  If fewer than *n* cycles exist
        in the tier, all available cycles are shown.
    seed : int, default 42
        Random seed passed to :meth:`pandas.DataFrame.sample` for
        reproducible sampling.
    label : str or None, default None
        Display label for the printed header.  Defaults to
        ``"QC tier <tier>"`` when ``None``.
    apply_wpl : bool, default False
        Forwarded to :func:`plot_cycle_diagnostics` for each cycle.

    Returns
    -------
    None
        Calls :func:`plot_cycle_diagnostics` for each sampled cycle.
        Prints a header line and skips chambers with no raw data loaded.

    Examples
    --------
    >>> from palmwtc.viz.diagnostics import show_sample_cycles
    >>> show_sample_cycles(data, raw_lookup, tier=1, n=3, seed=0)  # doctest: +SKIP
    """
    subset = data[data["flux_qc"] == tier]
    if subset.empty:
        print(f"No cycles for QC tier {tier}")
        return

    sample = subset.sample(n=min(n, len(subset)), random_state=seed)
    label = label or f"QC tier {tier}"
    print(f"{label} | n={len(sample)} | seed={seed}")
    for _, row in sample.iterrows():
        raw_df = raw_lookup.get(row["Source_Chamber"])
        if raw_df is None:
            continue
        plot_cycle_diagnostics(raw_df, row, apply_wpl=apply_wpl)
