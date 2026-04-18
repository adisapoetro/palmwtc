"""OOP entry point for QC processing.

Ported verbatim from ``flux_chamber/src/qc_functions.py`` (Phase 2).
``QCProcessor`` is the user-preferred OOP wrapper around the procedural
``process_variable_qc`` function (per CLAUDE.md §1: "OOP preferred").
"""

# ruff: noqa: RUF013
# Above ignores cover quirks carried verbatim from the original
# ``flux_chamber/src/qc_functions.py``: implicit ``Optional`` on
# ``random_seed: int = None`` and ``skip_persistence: list = None``.

from __future__ import annotations

import pandas as pd

from palmwtc.qc.rules import process_variable_qc


class QCProcessor:
    """
    Object-Oriented wrapper for quality control processing.
    Encapsulates the DataFrame and Configuration state to reduce argument passing
    between multiple QC steps.
    """

    def __init__(self, df: pd.DataFrame, config_dict: dict):
        self.df = df.copy()
        self.var_config_dict = config_dict

    def process_variable(
        self,
        var_name: str,
        random_seed: int = None,
        skip_persistence: list = None,
        skip_roc: list = None,
        use_sensor_exclusions: bool = False,
        exclusion_config_path=None,
    ) -> dict:
        """
        Executes the full QC pipeline for a single variable, returning the results and summary.
        Wraps the procedural `process_variable_qc` function.
        """
        skip_persistence = skip_persistence or []
        skip_roc = skip_roc or []

        result = process_variable_qc(
            self.df,
            var_name,
            self.var_config_dict,
            random_seed=random_seed,
            skip_persistence_for=skip_persistence,
            skip_rate_of_change_for=skip_roc,
            use_sensor_exclusions=use_sensor_exclusions,
            exclusion_config_path=exclusion_config_path,
        )

        # In a fully refactored state, this method would update self.df inplace
        # with the 'final_flags' from the result dictionary.

        flag_col = f"{var_name}_rule_flag"
        self.df[flag_col] = result["final_flags"]

        # Keep qc_flag in sync (base requirement from CLAUDE.md)
        qc_col = f"{var_name}_qc_flag"
        if qc_col in self.df.columns:
            self.df[qc_col] = self.df[[flag_col, qc_col]].max(axis=1)
        else:
            self.df[qc_col] = self.df[flag_col]

        return result

    def get_processed_dataframe(self) -> pd.DataFrame:
        """Returns the dataframe with updated flag columns."""
        return self.df
