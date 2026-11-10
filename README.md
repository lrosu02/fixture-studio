# Fixture Studio

A conversational CAD tool that turns an uploaded STEP part and a design brief into
a fixture you can inspect, revise and export as STEP. CadQuery/OpenCASCADE measures
the source; NVIDIA SMLib constructs the fixture through `usd-brep`.

**[Watch the video demonstration](FixtureStudio-demo.mp4)** ·
[Demo guide](demo/DEMO.md) · [Engineering notes](Notes.md)

![Motor and generated L-bracket](demo/motor-l-bracket.png)

The final submission is on **`main`**. Motors are one example: mounting geometry,
quantity and layout come from the uploaded part and the user's choices.

## Quick start

Verified on **Windows x64 with Python 3.12.10**. Install 64-bit Python 3.12 and the
[Microsoft Visual C++ Redistributable](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist),
then run in PowerShell:

```powershell
git clone https://github.com/lrosu02/fixture-studio.git
Set-Location fixture-studio
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts\prove_dependencies.py
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open **http://127.0.0.1:8501**. The pinned NVIDIA wheel includes SMLib and OpenUSD;
do not install a second `pxr`/OpenUSD runtime into this environment. Restart the
server after code updates; automatic source reload is disabled to keep active
CAD sessions consistent.

The wheel can print missing `pxr.*` Python-module warnings during successful native
USD I/O; the dependency proof checks the actual CAD round trip (details in Notes.md).

### Choose an assistant

| Mode | Setup | What to expect |
| --- | --- | --- |
| ChatGPT subscription (Codex CLI) | Install Codex CLI, run `codex login`, and verify `codex login status`. | Live planning and CAD feedback using subscription allowance. This integration has been exercised with real calls. |
| OpenAI API | Set `OPENAI_API_KEY` in the launching environment; optionally set `OPENAI_MODEL`. | Separate API billing. Implemented with test-double coverage; a live API-key call has not been verified. |
| Offline commands | No credential required. | Manual controls and a limited command parser; no conversational AI or AI review. |

Select the mode in the sidebar. If Codex is not on PATH, set `FIXTURE_CODEX_PATH`
to its executable. `.env` files are not loaded automatically. Live modes send
measured features, requirements, conversation and rendered review images to OpenAI;
they do not send the original STEP bytes. There is no automatic API fallback.

## Design workflow

1. **Upload a STEP.** Select its mounting/support face and any mounting holes in
   the 3D viewer. Selections save immediately. Parts without holes can use supported
   nests, trays or cylindrical retention.
2. **Describe the fixture.** In **Fixture goal**, enter the task, quantity, moving
   components, loads and service access. Choose the manufacturing method and click
   **Start design**. Answer the remaining questions together in the conversation.
3. **Generate a proposal.** Review the proposed dimensions and assumptions, then
   choose **Generate**. The app builds native CAD, checks it and requests AI feedback
   in a live mode. One bounded correction may adjust unlocked concept dimensions.
4. **Revise and add openings.** Use **Request a revision** or the thickness/dimension
   controls. After the first build, **Add a fixture opening** lets you click a flat
   fixture surface and choose a through-hole diameter. Changing fixture type keeps
   opening sizes but asks you to place them again on the new shape.
5. **Export STEP.** In the sidebar, select **Prepare STEP download**, then
   **Download STEP (.step)**. Saved projects and revision history support resume
   and restore; failed attempts retain the last valid fixture.

## Supported capabilities

| Area | Available today |
| --- | --- |
| Mounting structures | Common plates, parallel rails, ribbed L-brackets and bridge supports; row/grid layouts for 1–24 copies of one part. |
| Retention and bases | Hole-free trays, convex-envelope nests, cylindrical saddles/collars and split clamps; optional second STEP for an existing mounting base. |
| Hardware and access | Standard screw-clearance defaults, configurable base-hole counts, counterbores, countersinks, nut pockets, measured clearances and user-placed round through-holes. |
| Manufacturing | 3D printing and machining corner rules; sheet-metal panels with tab/slot allowances and welded joints; formed 90° L-bracket bends with separate ribs. |
| Review and revisions | Persistent 3D selection, colored assembly parts, editable dimensions and locks, geometric checks, AI feedback, revision comparison and restore. |

One uploaded STEP is treated as one part, preserving the relative positions of up
to 16 solids. Measurements and exports use millimeters. The geometry engine uses
validated data contracts and bounded operations; the AI does not execute arbitrary
modeling code. A bridge has a horizontal mounting platform, while an L-bracket has
an upright wall; switching between them can change the part's operating orientation.

## Exports

**STEP contains the generated fixture solids only**, excluding the uploaded part
and optional existing base. Separate welded panels remain separate solids in their
assembled positions. It transfers the actual SMLib BRep through an OpenCASCADE
writer, then reopens and checks the result; it is not a triangulated preview export.

**Export CAD + design record** provides native USD BRep, requirements, bounded
operations, measurements, validation and AI feedback. Prepare STEP first to include
the `.step` and its verification report in the ZIP. Pending openings are listed but
are absent from CAD until placed. Exports use the displayed saved revision, not
unbuilt changes to requirements. Original private STEP files are excluded.

## Reproduce and test

This deterministic demo needs no AI credential. It generates a bent sheet-metal
L-bracket, revises its thickness/joints, and prints the saved project, verified STEP
and design ZIP paths under `artifacts`:

```powershell
.\.venv\Scripts\python.exe scripts\demo_sheet_metal.py --bent
.\.venv\Scripts\python.exe scripts\reproduce.py demo\example-export.zip artifacts\reproduced
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests cover STEP measurement, native geometry, through-hole verification, revisions,
failure recovery, exports and UI behavior. Live model calls are opt-in and are not
part of the regression suite. With Node.js installed, run all viewer event checks:

```powershell
node --test tests/test_picker_pointer.mjs tests/test_mounting_picker.mjs tests/test_opening_picker.mjs
```

Additional deterministic examples and recorded live-call evidence are linked in
the [demo guide](demo/DEMO.md). Sample provenance is in [samples/PROVENANCE.md](samples/PROVENANCE.md).

## Limits

This is a fixture concept tool for the supported geometry families. Geometric
validation does not establish strength, fatigue, vibration, thermal behavior,
weld performance or a safe operating load. Source-to-fixture contact is sampled;
exact cross-kernel collision checking is not provided.

Mouse-placed openings currently support circular holes on flat, axis-aligned fixture
faces with sufficient edge clearance. Arbitrary freeform fixtures, concave conformal
nests, thread recognition, articulated clamps and mixed workpiece assemblies are
outside scope. Sheet-metal export includes formed/assembled geometry, not unfolded
blanks, DXF nesting or weld sizing. Native kernel process crashes are not fully isolated.

See [Notes.md](Notes.md) for architecture, decisions and verification evidence,
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for acceptance criteria, and
[CHANGELOG.md](CHANGELOG.md) for historical checkpoints.

For developers and agents, [STATE_MACHINES.md](STATE_MACHINES.md) maps the workflow,
selection, persistence and export lifecycles, including read-only JSON inspection.
