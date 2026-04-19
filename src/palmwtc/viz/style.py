"""
Plot style helpers for palmwtc visualisations.

Ported verbatim from ``flux_chamber/src/flux_visualization.py`` (``set_style``).

``set_style`` mutates the global seaborn theme + matplotlib rcParams.
It is side-effecting on import-time conventions used by the other
``palmwtc.viz`` sub-modules and by downstream notebooks.
"""

import matplotlib.pyplot as plt
import seaborn as sns


def set_style():
    sns.set_theme(style="whitegrid")
    plt.rcParams["figure.figsize"] = (12, 6)
