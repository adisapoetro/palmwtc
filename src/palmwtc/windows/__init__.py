"""palmwtc.windows — high-confidence calibration window selection.

Phase 2 ports from ``flux_chamber/src/window_selection.py``.
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
