"""palmwtc CLI entry point.

Subcommands:

- ``palmwtc info`` — print version + resolved DataPaths.
- ``palmwtc run`` — run the QC → flux → windows → validation pipeline.
  Library-mode by default; ``--notebooks`` switches to papermill mode.
- ``palmwtc sample {path,fetch}`` — bundled / downloadable sample helpers.

The Streamlit dashboard subcommand was removed in v0.2.0 — operational
monitoring is out of scope for the public package. The companion
flux_chamber working repo retains the LIBZ-specific dashboard.
"""

from __future__ import annotations

from pathlib import Path

import typer

from palmwtc import __version__
from palmwtc.config import DataPaths

app = typer.Typer(
    name="palmwtc",
    help="Automated whole-tree chamber workflow for oil-palm ecophysiology.",
    no_args_is_help=True,
    add_completion=False,
)
sample_app = typer.Typer(
    name="sample",
    help="Manage bundled and downloadable sample datasets.",
    no_args_is_help=True,
)
app.add_typer(sample_app, name="sample")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"palmwtc {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Print version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """palmwtc — automated whole-tree chamber workflow for oil-palm ecophysiology."""


@app.command()
def info(
    raw_dir: Path | None = typer.Option(
        None, "--raw-dir", help="Override raw data dir (else env / yaml / sample)."
    ),
    config_file: Path | None = typer.Option(
        None, "--config-file", help="Explicit palmwtc.yaml path."
    ),
) -> None:
    """Print version + resolved DataPaths."""
    typer.echo(f"palmwtc {__version__}")
    paths = DataPaths.resolve(raw_dir=raw_dir, config_file=config_file)
    typer.echo(paths.describe())


@app.command()
def run(
    raw_dir: Path | None = typer.Option(None, "--raw-dir", help="Override raw data dir."),
    config_file: Path | None = typer.Option(None, "--config-file", help="palmwtc.yaml path."),
    notebooks: bool = typer.Option(
        False, "--notebooks", help="Papermill mode (full notebook execution → HTML reports)."
    ),
    skip: list[str] = typer.Option(
        [],
        "--skip",
        help="Step names to skip (library mode: qc/flux/windows/validation; "
        "notebooks mode: numeric prefixes like 022 025).",
    ),
    only: list[str] = typer.Option(
        [],
        "--only",
        help="Run only these step names (library mode) or numeric prefixes (notebooks mode).",
    ),
    keep_going: bool = typer.Option(False, "--keep-going", help="Continue past failed steps."),
    timeout: int = typer.Option(
        1800, "--timeout", help="Per-notebook timeout in seconds (notebooks mode only)."
    ),
    parallel: int = typer.Option(
        1,
        "--parallel",
        help="Worker count for non-spine notebooks (notebooks mode only; default 1).",
    ),
) -> None:
    """Run the QC → flux → windows → validation pipeline."""
    paths = DataPaths.resolve(raw_dir=raw_dir, config_file=config_file)
    typer.echo(f"palmwtc run | {paths.source}")
    typer.echo(f"  raw_dir = {paths.raw_dir}")
    typer.echo(f"  exports_dir = {paths.exports_dir}")

    if notebooks:
        from palmwtc.notebooks_runner import run_notebooks

        nb_dir_str = paths.extras.get("notebooks_dir") if paths.extras else None
        if nb_dir_str:
            nb_dir = Path(nb_dir_str).expanduser().resolve()
        else:
            typer.secho(
                "  [error] --notebooks mode requires a 'notebooks_dir' entry in palmwtc.yaml "
                "or an env override; the bundled sample has no notebooks bundled yet "
                "(those land in Phase 4).",
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)

        results = run_notebooks(
            notebooks_dir=nb_dir,
            output_dir=paths.exports_dir / "executed",
            only=[int(x) for x in only] if only else None,
            skip=[int(x) for x in skip] if skip else None,
            timeout=timeout,
            keep_going=keep_going,
            parallel=parallel,
        )
        n_fail = sum(1 for r in results if not r.ok)
        raise typer.Exit(code=1 if n_fail else 0)

    # Library mode (default)
    from palmwtc.pipeline import run_pipeline

    result = run_pipeline(
        paths,
        steps=only or None,
        skip=skip or None,
        keep_going=keep_going,
    )
    typer.echo(result.summary())
    raise typer.Exit(code=0 if result.ok else 1)


@sample_app.command("path")
def sample_path() -> None:
    """Print the on-disk path to the bundled synthetic sample directory."""
    from palmwtc.data import sample_dir

    typer.echo(str(sample_dir("synthetic")))


@sample_app.command("fetch")
def sample_fetch(
    kind: str = typer.Argument("real", help="Sample kind to fetch (currently 'real' from Zenodo)."),
) -> None:
    """Download the real-downsampled LIBZ sample from Zenodo. (Stub — Phase 7.)"""
    typer.secho(
        f"sample fetch '{kind}' not yet implemented — Zenodo wiring lands in Phase 7. "
        f"Bundled synthetic sample is already on disk at:",
        fg=typer.colors.YELLOW,
    )
    sample_path()
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
