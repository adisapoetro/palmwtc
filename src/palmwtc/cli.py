"""palmwtc CLI entry point. Phase 1 skeleton — subcommands are stubs.

Real implementations land in Phase 3 (config + pipeline + sample fetch wiring).
"""

from __future__ import annotations

import typer

from palmwtc import __version__

app = typer.Typer(
    name="palmwtc",
    help="Automated whole-tree chamber workflow for oil-palm ecophysiology.",
    no_args_is_help=True,
    add_completion=False,
)


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
    pass


@app.command()
def info() -> None:
    """Print package version + resolved configuration. (Phase 1 stub.)"""
    typer.echo(f"palmwtc {__version__}")
    typer.echo("(Phase 1 skeleton — DataPaths resolver lands in Phase 3)")


@app.command()
def run(
    skip: list[str] | None = typer.Option(
        None, "--skip", help="Pipeline step prefixes to skip (e.g. 022 025)."
    ),
    notebooks: bool = typer.Option(
        False, "--notebooks", help="Papermill mode (executes notebooks → HTML reports)."
    ),
    sample: bool = typer.Option(
        False, "--sample", help="Force use of bundled synthetic sample dataset."
    ),
) -> None:
    """Run the full QC → flux → validation pipeline. (Phase 1 stub.)"""
    typer.echo("Pipeline not yet implemented — see Phase 3 of the extraction plan.")
    typer.echo(f"  skip={skip} notebooks={notebooks} sample={sample}")
    raise typer.Exit(code=2)


@app.command()
def dashboard() -> None:
    """Launch the streamlit monitoring dashboard. (Phase 1 stub; Phase 6 wires it up.)"""
    typer.echo("Dashboard not yet wired — see Phase 6 of the extraction plan.")
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
