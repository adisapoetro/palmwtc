"""
Cycle-level diagnostic plots for chamber flux QC review.

Ported verbatim from ``flux_chamber/src/flux_visualization.py`` — the
"Cycle Diagnostic Plots" block plus ``plot_chamber_resizing_validation``.

Includes:

- ``plot_cycle_diagnostics`` — fit + residual panels for a single cycle.
- ``plot_specific_cycle`` — locate a cycle by chamber + datetime string.
- ``plot_cycle_by_id`` — locate a cycle by chamber + cycle_id.
- ``show_sample_cycles`` — show ``n`` random cycles for a QC tier.
- ``plot_chamber_resizing_validation`` — +/- 60 day window around the
  chamber resizing date to inspect for artefacts.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def plot_chamber_resizing_validation(flux_df, resize_date="2025-07-01", variable="flux_absolute"):
    """
    Visualizes signal around the chamber resizing event to check for artifacts. Faceted.
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


def plot_cycle_diagnostics(raw_df, flux_row, apply_wpl=False):
    """
    Plot single cycle with fit line, residuals, and optional WPL info.

    Parameters
    ----------
    raw_df : pd.DataFrame
        Raw chamber data (from ``prepare_chamber_data``).
    flux_row : pd.Series
        Single row from flux results DataFrame.
    apply_wpl : bool
        If True, label traces assuming WPL correction was applied.
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


def plot_specific_cycle(data, raw_lookup, chamber, date_str, apply_wpl=False):
    """
    Plot diagnostics for a specific cycle by chamber and datetime string.

    Parameters
    ----------
    date_str : str
        Format: ``"DD/MM/YY HH:MM:SS"`` (dayfirst).
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


def plot_cycle_by_id(data, raw_lookup, chamber, cycle_id, apply_wpl=False):
    """Plot diagnostics for a specific cycle by chamber and cycle_id."""
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


def show_sample_cycles(data, raw_lookup, tier, n=5, seed=42, label=None, apply_wpl=False):
    """Show random sample of cycles for a QC tier."""
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
