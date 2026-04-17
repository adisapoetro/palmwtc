# Contributing to palmwtc

Thanks for considering a contribution. `palmwtc` is a small scientific-Python
project and we want to keep it easy to run, easy to audit, and easy to cite.

## Quick start

```bash
git clone git@github.com:adisapoetro/palmwtc.git
cd palmwtc
uv sync --all-extras            # installs everything + dev tools
uv run pytest                   # all tests pass on fresh checkout
uv run palmwtc run              # runs pipeline on bundled synthetic sample
```

If you don't have `uv`, `pip install -e '.[dev]'` works too.

## Dev workflow

1. **Branch from `main`** for any non-trivial change:
   `git checkout -b feat/short-description` or `fix/short-description`.
2. **Keep changes small**. One logical change per PR. If it needs a design
   conversation, open an issue first.
3. **Run locally before pushing**:
   ```bash
   uv run ruff check src/ tests/
   uv run ruff format src/ tests/ --check
   uv run mypy src/palmwtc
   uv run pytest
   ```
   `pre-commit` hooks run these automatically on commit. Install with
   `uv run pre-commit install`.
4. **Conventional Commits** for commit messages:
   `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `ci:`.
5. **Scientific integrity rule**: every numerical claim added to docs or
   notebooks must trace to either (a) a `file.py:line` reference,
   (b) an executed notebook output, or (c) a cited publication. No
   invented numbers. (Inherited from the upstream flux_chamber project.)

## Opening a PR

- Title: Conventional-Commits style (e.g. `feat: add drift correction to QC`).
- Description: what changed, why, how to verify.
- CI must be green (lint + typecheck + test + docs-build + pipeline-smoke).
- Tag `@adisapoetro` for review.

## Reporting bugs

Open an issue at
[github.com/adisapoetro/palmwtc/issues](https://github.com/adisapoetro/palmwtc/issues).
Include:

- `palmwtc --version`
- Python version, OS
- A minimal reproducer (code + the data shape it runs against, or
  `palmwtc run --sample` if it reproduces on the bundled sample)
- Full traceback or unexpected output

## Scientific contributions

If you are proposing a change to QC thresholds, flux calculation, or
ecophysiology validation bounds:

1. Reference the publication or measurement study justifying the new value.
2. Add a row to `CHANGELOG.md` under a `### Science` subheading.
3. Update the literature-comparison table in the relevant doc page if it
   exists (see `docs/science/`).

## License

By contributing, you agree your contribution is licensed under the MIT License
(see [`LICENSE`](LICENSE)).
