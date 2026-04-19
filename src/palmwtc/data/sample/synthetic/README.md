# palmwtc bundled synthetic sample

Deterministic (SEED=42) synthetic dataset for CI smoke + zero-config first-run.

- 7 days × 30s sampling = 20160 chamber rows.
- 2 chambers (C1, C2), 30-min cycles (10 closed / 20 open).
- 30-min weather, 2 baseline tree biophysics rows.

Edge cases injected: {'nan_burst': {'variable': 'CO2_C1', 'start': '2026-03-03 12:00:00', 'minutes': 45}, 'drift': {'variable': 'CO2_C2', 'start': '2026-03-05 00:00:00', 'rate': '+0.5 ppm/day'}, 'spike_co2': {'variable': 'CO2_C1', 'start': '2026-03-06 10:00:00', 'value': 800.0}, 'spike_h2o': {'variable': 'H2O_C2', 'start': '2026-03-07 14:00:00', 'value': -5.0}, 'saturation': {'variable': 'H2O_C1', 'start': '2026-03-04 03:00:00', 'value': 60.0}}

Regenerate with `python scripts/make_sample_data.py`.
