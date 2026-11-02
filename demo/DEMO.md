# Demonstration and reproduction

The completed user-recorded demonstration is available as
**[FixtureStudio-demo.mp4](../FixtureStudio-demo.mp4)**. GitHub offers a download
if playback is unavailable. The current application and recording are on `main`.

## Run a deterministic example

After following the [quick start](../README.md#quick-start), run:

```powershell
.\.venv\Scripts\python.exe scripts\demo_sheet_metal.py --bent
```

This uses a synthetic sample to generate a formed L-bracket, change its sheet
thickness and joints, and export verified STEP for both revisions. The script
prints its saved project, STEP and ZIP paths under `artifacts`. Resume the printed
project from the app sidebar to inspect the revisions. Omit `--bent` for separate
tabbed/welded panels.

Other examples:

| Command | Coverage |
| --- | --- |
| `python scripts/demo.py` | Six synthetic parts, plate-to-rails revision, native export and HTML viewer. Updates the bundled files under `demo`. |
| `python scripts/demo_extensions.py` | Connector/base mounting, split clamp and convex-envelope nest with STEP exports. |
| `python scripts/reproduce.py demo/example-export.zip artifacts/reproduced` | Rebuild an existing export from its saved, bounded operation plan. |

Use `.\.venv\Scripts\python.exe` for these commands when the virtual environment
is not activated. These examples make **no live AI calls**. Their selected sizes
and quantities are scenario inputs, not hardcoded application decisions.

## Exercise the live conversation

Choose an authenticated assistant in the sidebar, upload a STEP or load a bundled
example, and select a mounting face and any part screw holes. Enter the task and
operating context in **Fixture goal**, then select **Start design**. Answer the
grouped questions, choose a proposal and generate it. Request a dimensional or
layout revision, inspect the result, and prepare/download its STEP.

The [README workflow](../README.md#design-workflow) describes the current controls.
For a scripted live subscription check:

```powershell
.\.venv\Scripts\python.exe scripts\prove_subscription.py --full
```

This requires Codex CLI ChatGPT sign-in, makes real cloud calls and consumes
subscription allowance. Offline mode does not substitute for this integration.

## Recorded evidence

- [Live planning and revision record](live-subscription-record.json) and
  [native export](live-subscription-export.zip).
- [Live CAD feedback record](live-feedback-record.json) and
  [reviewed export](live-feedback-export.zip).
- [Live L-bracket record](live-l_bracket-record.json) and
  [native export](live-l_bracket-export.zip).
- [Interactive assembly](assembly.html) from the deterministic six-part example;
  download and open locally to interact with it.

These records and screenshots capture earlier verification runs. They are evidence
of those runs, rather than a guarantee that a new model call returns the same prose.
Synthetic samples and their sources are documented in
[PROVENANCE.md](../samples/PROVENANCE.md).
