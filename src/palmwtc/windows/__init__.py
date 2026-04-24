"""palmwtc.windows — high-confidence calibration window selection.

This subpackage selects contiguous date ranges ("windows") of oil-palm
chamber cycles whose per-cycle quality scores are high enough to use as
training data for the XPalm digital-twin model.

Main entry point
----------------
:class:`~palmwtc.windows.selector.WindowSelector`
    Multi-criteria selector that scores cycles, detects instrument drift,
    and packages qualifying windows as a cycle CSV and JSON manifest.

Module-level helper
-------------------
:func:`~palmwtc.windows.selector.merge_sensor_qc_onto_cycles`
    Vectorized interval-join that appends per-cycle mean CO₂/H₂O sensor
    QC flags from the high-frequency 021 parquet onto the cycle DataFrame.

Configuration
-------------
:data:`~palmwtc.windows.selector.DEFAULT_CONFIG`
    Dict of all tunable thresholds with documented physical meaning.
    Pass ``config={"key": value}`` to :class:`WindowSelector` to override
    individual keys.

Typical usage::

    from palmwtc.windows import WindowSelector

    ws = WindowSelector(cycles_df, config={"min_window_days": 7})
    ws.detect_drift()
    ws.score_cycles()
    ws.identify_windows()
    filtered_df, manifest = ws.export()
"""

from palmwtc.windows.selector import (
    DEFAULT_CONFIG,
    WindowSelector,
    merge_sensor_qc_onto_cycles,
)

__all__ = [
    "DEFAULT_CONFIG",
    "WindowSelector",
    "merge_sensor_qc_onto_cycles",
]
