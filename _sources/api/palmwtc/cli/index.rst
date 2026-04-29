palmwtc.cli
===========

.. py:module:: palmwtc.cli

.. autoapi-nested-parse::

   palmwtc CLI entry point.

   Subcommands:

   - ``palmwtc info`` — print version + resolved DataPaths.
   - ``palmwtc run`` — run the QC → flux → windows → validation pipeline.
     Library-mode by default; ``--notebooks`` switches to papermill mode.
   - ``palmwtc sample {path,fetch}`` — bundled / downloadable sample helpers.

   The Streamlit dashboard subcommand was removed in v0.2.0 — operational
   monitoring is out of scope for the public package. The companion
   flux_chamber working repo retains the LIBZ-specific dashboard.



Attributes
----------

.. autoapisummary::

   palmwtc.cli.app
   palmwtc.cli.sample_app


Functions
---------

.. autoapisummary::

   palmwtc.cli._version_callback
   palmwtc.cli._main
   palmwtc.cli.info
   palmwtc.cli.run
   palmwtc.cli.sample_path


Module Contents
---------------

.. py:data:: app

.. py:data:: sample_app

.. py:function:: _version_callback(value: bool) -> None

.. py:function:: _main(version: bool = typer.Option(False, '--version', '-V', help='Print version and exit.', callback=_version_callback, is_eager=True)) -> None

   palmwtc — automated whole-tree chamber workflow for oil-palm ecophysiology.


.. py:function:: info(raw_dir: pathlib.Path | None = typer.Option(None, '--raw-dir', help='Override raw data dir (else env / yaml / sample).'), config_file: pathlib.Path | None = typer.Option(None, '--config-file', help='Explicit palmwtc.yaml path.')) -> None

   Print version + resolved DataPaths.


.. py:function:: run(raw_dir: pathlib.Path | None = typer.Option(None, '--raw-dir', help='Override raw data dir.'), config_file: pathlib.Path | None = typer.Option(None, '--config-file', help='palmwtc.yaml path.'), notebooks: bool = typer.Option(False, '--notebooks', help='Papermill mode (full notebook execution → HTML reports).'), skip: list[str] = typer.Option([], '--skip', help='Step names to skip (library mode: qc/flux/windows/validation; notebooks mode: numeric prefixes like 022 025).'), only: list[str] = typer.Option([], '--only', help='Run only these step names (library mode) or numeric prefixes (notebooks mode).'), keep_going: bool = typer.Option(False, '--keep-going', help='Continue past failed steps.'), timeout: int = typer.Option(1800, '--timeout', help='Per-notebook timeout in seconds (notebooks mode only).'), parallel: int = typer.Option(1, '--parallel', help='Worker count for non-spine notebooks (notebooks mode only; default 1).')) -> None

   Run the QC → flux → windows → validation pipeline.


.. py:function:: sample_path() -> None

   Print the on-disk path to the bundled synthetic sample directory.


