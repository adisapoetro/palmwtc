"""matplotlib style defaults for palmwtc figures.

Applies a consistent look-and-feel (font sizes, grid, color cycle) so
static plots produced by :mod:`palmwtc.viz.timeseries`,
:mod:`palmwtc.viz.diagnostics`, and :mod:`palmwtc.viz.qc_plots` share
a visual identity.
"""

import matplotlib.pyplot as plt
import seaborn as sns


def set_style() -> None:
    """Apply the standard palmwtc matplotlib/seaborn theme.

    Sets the seaborn ``"whitegrid"`` theme and fixes the default figure size
    to ``(12, 6)`` inches.  Call this once at the top of a notebook or script
    before producing any plots.

    Returns
    -------
    None
        This function returns nothing.  It modifies global matplotlib
        rcParams and the seaborn theme as a side effect.

    Notes
    -----
    This function is **side-effecting**: it changes ``matplotlib.rcParams``
    and the active seaborn theme for the entire Python session.  Any plots
    created after calling this function will use the new settings.  To undo,
    call ``matplotlib.rcdefaults()`` or ``seaborn.reset_defaults()``.

    The function is idempotent — calling it multiple times has the same
    result as calling it once.

    Examples
    --------
    >>> from palmwtc.viz.style import set_style
    >>> set_style()  # doctest: +SKIP
    """
    sns.set_theme(style="whitegrid")
    plt.rcParams["figure.figsize"] = (12, 6)
