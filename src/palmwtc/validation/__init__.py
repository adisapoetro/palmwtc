"""palmwtc.validation — science validation against literature ecophysiology bounds.

Phase 2 ports from ``flux_chamber/src/science_validation.py``.
"""

from palmwtc.validation.science import (
    DEFAULT_CONFIG,
    derive_is_daytime,
    run_science_validation,
)

__all__ = ["DEFAULT_CONFIG", "derive_is_daytime", "run_science_validation"]
