palmwtc.qc.processor
====================

.. py:module:: palmwtc.qc.processor

.. autoapi-nested-parse::

   Stateful orchestrator for whole-tree chamber QC processing.

   :class:`QCProcessor` is the user-facing object-oriented entry point for
   running the quality-control pipeline on a sensor dataframe. It wraps the
   procedural :func:`~palmwtc.qc.rules.process_variable_qc` function and keeps
   the growing flag columns in one place so callers do not need to pass the
   dataframe back and forth between steps.

   Typical workflow::

       qc = QCProcessor(df=raw_df, config_dict=VAR_CONFIG)
       result = qc.process_variable("CO2_LI850")
       result2 = qc.process_variable("H2O_LI850")
       flagged_df = qc.get_processed_dataframe()



Classes
-------

.. autoapisummary::

   palmwtc.qc.processor.QCProcessor


Module Contents
---------------

.. py:class:: QCProcessor(df: pandas.DataFrame, config_dict: dict)

   Object-oriented wrapper for the whole-tree chamber QC pipeline.

   Stores the working dataframe and variable configuration so callers do not
   need to pass them to every function call. Call :meth:`process_variable`
   once per sensor column; the resulting flag columns accumulate in
   :attr:`df`. Retrieve the final annotated dataframe with
   :meth:`get_processed_dataframe`.

   Parameters
   ----------
   df : pd.DataFrame
       Raw or lightly pre-processed sensor dataframe. The index may be a
       ``DatetimeTZIndex`` or a plain ``RangeIndex``; a ``TIMESTAMP`` column
       is supported as well. The dataframe is copied on construction so the
       original is never mutated.
   config_dict : dict
       Variable-level QC configuration. Keys are arbitrary config-group
       names (e.g. ``"co2"``). Each value is a sub-dict that must contain
       either ``"columns": [list-of-column-names]`` or
       ``"pattern": "<prefix>"`` (for soil sensor arrays whose column names
       share a common prefix) plus physical limit keys such as ``"hard"``
       and ``"soft"``. Passed directly to
       :func:`~palmwtc.qc.rules.get_variable_config`; see that function for
       the full schema.

   Attributes
   ----------
   df : pd.DataFrame
       Working copy of the input dataframe. Grows one ``{var}_rule_flag``
       column (and updates or creates ``{var}_qc_flag``) each time
       :meth:`process_variable` is called.
   var_config_dict : dict
       The configuration dict passed at construction, stored unchanged.

   Methods
   -------
   process_variable(var_name, ...)
       Run the full QC pipeline for one variable and store the flags in
       :attr:`df`.
   get_processed_dataframe()
       Return :attr:`df` with all flag columns added so far.

   Examples
   --------
   Build a tiny sensor dataframe and run QC on one column:

   >>> import pandas as pd
   >>> import numpy as np
   >>> from palmwtc.qc.processor import QCProcessor
   >>> rng = np.random.default_rng(0)
   >>> df = pd.DataFrame({"CO2_LI850": rng.uniform(350, 450, 20)})
   >>> # config_dict keys are config-group names; each entry lists the
   >>> # variable columns it covers via "columns" or "pattern".
   >>> config = {
   ...     "co2": {
   ...         "columns": ["CO2_LI850"],
   ...         "hard": [300, 600],
   ...         "soft": [350, 550],
   ...         "rate_of_change": {"limit": 50},
   ...         "persistence": {"window": 5},
   ...     }
   ... }
   >>> qc = QCProcessor(df=df, config_dict=config)
   >>> result = qc.process_variable("CO2_LI850", random_seed=42)
   >>> "CO2_LI850_rule_flag" in qc.df.columns
   True
   >>> set(qc.df["CO2_LI850_rule_flag"].unique()).issubset({0, 1, 2})
   True


   .. py:attribute:: df


   .. py:attribute:: var_config_dict


   .. py:method:: process_variable(var_name: str, random_seed: int = None, skip_persistence: list = None, skip_roc: list = None, use_sensor_exclusions: bool = False, exclusion_config_path=None) -> dict

      Run the full QC pipeline for one variable and store flags in :attr:`df`.

      Delegates to :func:`~palmwtc.qc.rules.process_variable_qc` with the
      configuration slice for *var_name* from :attr:`var_config_dict`. After
      the call the flag columns ``{var_name}_rule_flag`` and
      ``{var_name}_qc_flag`` are written into :attr:`df` in place.

      Parameters
      ----------
      var_name : str
          Column name in :attr:`df` to process (e.g. ``"CO2_LI850"``).
      random_seed : int, optional
          Seed passed to the Isolation Forest (ML outlier step). ``None``
          means non-deterministic.
      skip_persistence : list of str, optional
          Variable names for which the persistence (stuck-sensor) check is
          bypassed. Defaults to an empty list.
      skip_roc : list of str, optional
          Variable names for which the rate-of-change spike check is
          bypassed. Defaults to an empty list.
      use_sensor_exclusions : bool, default False
          If ``True``, load a YAML sensor-exclusion config and apply
          exclusion flags before combining.
      exclusion_config_path : path-like or None, optional
          Path to the YAML exclusion config file. Only used when
          *use_sensor_exclusions* is ``True``. If ``None`` the default
          location resolved by :func:`~palmwtc.qc.rules.process_variable_qc`
          is used.

      Returns
      -------
      dict
          Result dict from :func:`~palmwtc.qc.rules.process_variable_qc`
          with at least the following keys:

          ``"final_flags"`` : pd.Series
              Integer flag series (0 = good, 1 = suspect, 2 = bad).
          ``"summary"`` : dict
              Per-flag counts and percentages; keys are
              ``"total_points"``, ``"flag_0_count"``, ``"flag_0_percent"``,
              ``"flag_1_count"``, ``"flag_1_percent"``,
              ``"flag_2_count"``, ``"flag_2_percent"``.
          ``"bounds_flags"`` : pd.Series
              Raw flags from the physical-bounds check (may be absent if
              the step was skipped).
          ``"iqr_flags"`` : pd.Series
              Raw flags from the IQR outlier check (may be absent).

      Raises
      ------
      KeyError
          If *var_name* is not found in :attr:`var_config_dict`.

      Examples
      --------
      >>> import pandas as pd
      >>> import numpy as np
      >>> from palmwtc.qc.processor import QCProcessor
      >>> df = pd.DataFrame({"H2O_LI850": np.linspace(10, 30, 20)})
      >>> config = {
      ...     "h2o": {
      ...         "columns": ["H2O_LI850"],
      ...         "hard": [0, 50],
      ...         "soft": [1, 45],
      ...         "rate_of_change": {"limit": 10},
      ...         "persistence": {"window": 5},
      ...     }
      ... }
      >>> qc = QCProcessor(df=df, config_dict=config)
      >>> result = qc.process_variable("H2O_LI850", random_seed=0)
      >>> isinstance(result, dict)
      True
      >>> "final_flags" in result
      True



   .. py:method:: get_processed_dataframe() -> pandas.DataFrame

      Return the working dataframe with all QC flag columns added so far.

      Returns
      -------
      pd.DataFrame
          The internal :attr:`df` copy, which includes one
          ``{var}_rule_flag`` column and one ``{var}_qc_flag`` column for
          each variable processed with :meth:`process_variable`.

      Examples
      --------
      >>> import pandas as pd
      >>> import numpy as np
      >>> from palmwtc.qc.processor import QCProcessor
      >>> df = pd.DataFrame({"CO2_LI850": np.linspace(380, 420, 10)})
      >>> config = {
      ...     "co2": {
      ...         "columns": ["CO2_LI850"],
      ...         "hard": [300, 600],
      ...         "soft": [350, 550],
      ...         "rate_of_change": {"limit": 50},
      ...         "persistence": {"window": 5},
      ...     }
      ... }
      >>> qc = QCProcessor(df=df, config_dict=config)
      >>> _ = qc.process_variable("CO2_LI850", random_seed=0)
      >>> out = qc.get_processed_dataframe()
      >>> "CO2_LI850_qc_flag" in out.columns
      True



