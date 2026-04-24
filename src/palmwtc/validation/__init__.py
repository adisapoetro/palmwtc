# ruff: noqa: RUF002
"""palmwtc.validation — science validation against literature ecophysiology bounds.

This subpackage compares per-cycle CO₂ and H₂O flux results against published
ecophysiology values for tropical oil-palm canopies.  It is designed to be
called after :mod:`palmwtc.windows` has selected high-confidence cycles.

Main entry point
----------------
:func:`~palmwtc.validation.science.run_science_validation`
    Run all four ecophysiology checks in one call and return a structured
    scorecard dict.  Each check returns ``"PASS"``, ``"BORDERLINE"``,
    ``"FAIL"``, or ``"N/A"`` (when data are insufficient).

Checks performed
~~~~~~~~~~~~~~~~
1. **Light response** — Amax and quantum yield (alpha) within whole-canopy
   bounds for tropical perennial crops (Lamade & Bouillet 2005).
2. **Q10 temperature response** — respiration Q10 within 1.5–3.0.
3. **Water use efficiency (WUE)** — median WUE in range and negative WUE–VPD
   correlation consistent with Medlyn stomatal optimality (Medlyn et al. 2011).
4. **Inter-chamber agreement** — daytime Pearson r > 0.70 between the two
   automated whole-tree chambers.

Helper
------
:func:`~palmwtc.validation.science.derive_is_daytime`
    Classify cycles as day/night using global radiation, with hour-of-day
    as a fallback when radiation data are absent.

Configuration
-------------
:data:`~palmwtc.validation.science.DEFAULT_CONFIG`
    Dict of all configurable column names and literature-cited thresholds.

Typical usage::

    from palmwtc.validation import run_science_validation

    result = run_science_validation(cycles_df, label="cycle_conf=0.65")
    print(result["scorecard"])
"""

from palmwtc.validation.science import (
    DEFAULT_CONFIG,
    derive_is_daytime,
    run_science_validation,
)

__all__ = ["DEFAULT_CONFIG", "derive_is_daytime", "run_science_validation"]
