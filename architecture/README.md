# architecture/

Project dashboard for `palmwtc`. Two consumers:

- **Agents** read [`architecture.json`](architecture.json) and [`pulse.json`](pulse.json) — machine view, the canonical sources of truth.
- **Humans** open [`architecture.html`](architecture.html) in a browser — interactive viewer with a `Pulse` tab (state), `Stack` tab (structure), and conditional tabs based on what data exists.

## File layout

```
architecture.json     ← slow-changing structure (hand-edit)
pulse.json            ← fast-changing state (hand-edit)
architecture.data.js  ← autogen: sets window.ARCH_DATA = <json>
pulse.data.js         ← autogen: sets window.PULSE_DATA = <json + git block>
architecture.html     ← shell (loads both data files + viewer)
architecture.css      ← styles, hand-edit
architecture.js       ← render logic, hand-edit
build.py              ← regenerates both .data.js files; auto-fills git block in pulse.data.js
```

Why the sidecar `*.data.js`? `fetch('*.json')` is blocked by `file://` CORS in Chrome/Firefox, so each JSON is wrapped in a `window.X_DATA = …` assignment and loaded via `<script src>`. Works everywhere with no setup.

## Editing workflow

| You want to update… | Edit | Then run |
|---|---|---|
| What's in flight, blockers, recent decisions | `pulse.json` | `python architecture/build.py` |
| Layer map, module roles, schemas, privacy | `architecture.json` | `python architecture/build.py` |

Refresh the browser. Done.

For style or interactivity changes, edit `architecture.css` or `architecture.js` directly.

## Pulse schema

See [the skill reference](~/.claude/skills/project-dashboard/references/pulse_schema.md) for field-by-field documentation.

## Keyboard shortcuts (viewer)

- `1`–`9` — jump between tabs
- `/` — focus the current tab's search box
- Click any commit SHA, module path, or freshness badge → copies to clipboard

## Drift discipline

The viewer reads `window.ARCH_DATA` and `window.PULSE_DATA` at runtime, so the JSON and the rendered view cannot drift as long as `build.py` is re-run after JSON edits. Consider adding a pre-commit hook that re-runs `build.py` and stages the resulting `.data.js` files.

## Cross-project meta-index

Your `pulse.json` is also read by `~/Projects/index.html` (regenerate with `python ~/.claude/skills/project-dashboard/scripts/build_index.py`). Keep `status`, `blockers`, and `next_milestone` honest — the meta-index sorts on them.
