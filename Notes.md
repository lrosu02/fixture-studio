# Engineering record

Fixture Studio implements the concept in IMPLEMENTATION_PLAN.md: a reusable
conversational fixture tool, with a synthetic six-part case as a demonstration.
No dimensions, quantities, bolt circles or mounting conclusions from the sample
are embedded in general application logic. Sample-specific values live in the
sample generator, test fixtures and demo scripts only.

## Checkpoint and total time — October 30, 2026

**Cumulative project time reported by the user: 3 hours 30 minutes (3.5 hours).**
This is the current total through the working, publicly published baseline. It
supersedes earlier statements that a total had not been supplied. Historical timed
intervals below describe subsets of the work; do not add them to this cumulative
total. A breakdown between human effort, agent execution and waiting was not supplied.

The delivered application imports/measures STEP, supports face and hole selection,
captures manufacturing intent and conversational requirements, proposes supported
fixtures, builds them in SMLib, checks and reviews them with AI, preserves revisions
and exports verified STEP plus the native CAD/design record. Geometry includes
plates, rails, L-brackets, bridges and hole-free rectangular locating/strap trays.
Standard clearance sizing, configurable base-hole counts and through cable passages
are implemented. Public source publication and a fresh clone have been verified.

Verification at this checkpoint: **126 tests passed in 136.68 seconds**, followed
by **8 workflow tests passed in 9.16 seconds** for the final Start design prompt
change; these are overlapping runs, not 134 distinct tests. Ruff F checks passed.
Live subscription workflows cover the earlier screw-mounted examples. Hole-free
trays have native geometry, STEP and UI regression coverage, but no new live AI run
is claimed for that extension.

Remaining delivery gap: the continuous demo recording. Live API-key verification
and broader geometry/physical analysis also remain unverified or unsupported as
documented below. Click-to-select openings/keep-clear areas is the suggested next
feature, not part of this checkpoint. See the [plan checkpoint](IMPLEMENTATION_PLAN.md#implementation-checkpoint--october-30-2026)
for stage status and the candidate backlog.

## Hole-free support faces and locating trays (2026-10-30)

Analysis version 2 retains every measured planar face, including faces without
circular holes. Existing hole-based automatic recommendations remain unchanged;
blank support faces require explicit user selection. The same face picker and
fixture-side arrow apply. Empty hole selections now lead to an explicit retention
choice instead of silently selecting all holes. Old version-1 analyses remain
readable; re-uploading the source is required to expose their previously omitted faces.

Compiler version 8 adds rectangular locating trays and trays with external-strap
slots using the existing SMLib stock/support/union/relief vocabulary. Whole-part
bounds in the selected face frame determine the tray envelope, repeated placement
spacing and wall positions. An outer support plane is required; a source protruding
behind it is rejected. No source screw holes are synthesized. Base bolt sizing is
independent and must be supplied when there are no known part fasteners.

The new requirement fields are part_attachment (screws/unselected/cradle/strap),
locating_clearance, locating_wall, locating_height, strap_width and strap_thickness.
Defaults are 0.5 mm fit clearance, 3 mm wall thickness and a wall height of the
smaller of 5 mm or half the measured part height. Strap slots add 1 mm to the
user-supplied strap dimensions and retain 2 mm side lands. These are editable
concept assumptions, not validated printing compensation or strength dimensions.
Existing projects default to screw attachment and historical compiler versions
retain their prior operations. Face changes clear incompatible old-frame choices;
requirement locks, revisions and restore remain enforced.

Native validation independently derives required walls and full-depth slot sweeps,
checks material coverage and obstruction, checks the measured whole-part bounding
envelope above its support plane, and samples up to 32 trimmed face centroids for
contact. Deliberately shortened walls and blind slots fail. Screw-specific checks
are marked not evaluated when there are no source mounting holes. Open trays provide
no hold-down; strap hardware, its tension/strength and underside installation are
not simulated. These are rectangular fixtures, not conformal nests or articulated
clamps. The AI receives these capabilities and asks about retention/access as
application requirements; no successful new live AI run is claimed for this feature.

The original synthetic hole_free_housing.step and its generator are bundled.
Tests exercised cradle and strap variants, two-part placement, transformed source
invariance, real STEP export/reopening, absence of invented part holes, independently
probed through slots, fault injection, revised fit clearance, restore/locks and the
Streamlit face-confirmation/retention controls. The full suite passed **126 tests
in 136.68 seconds**; Ruff F checks passed. Native fixture construction remains SMLib.
Elapsed development time for this follow-up was not separately clocked.
The final Start design prompt adjustment also passed all eight workflow tests.

## Public repository and terminal Git setup (2026-10-30)

Source repository: https://github.com/lrosu02/fixture-studio (public).
Git 2.55.0 was already installed; GitHub CLI 2.103.3 was installed from the official
WinGet GitHub.cli package and authenticated by the user through device authorization.
Credentials remain in the Windows keyring, outside the repository. Terminal Git uses
the CLI credential helper. Only this project path was added to Git's safe.directory
list because its drive does not record filesystem ownership. Commit identity uses
the account's GitHub noreply address.

The reviewed source set includes application code, tests, documentation and permitted
synthetic specimens/demo exports. Local environments, private uploaded/generated
projects, logs, .env and Streamlit secrets are ignored; the source ZIP also excludes
secret configuration files. Bundled export source identities are the synthetic motor
and sensor bracket. STEP bytes are exempt from line-ending conversion so file hashes
remain stable across checkouts. No dependency binaries are vendored.

## Base-hole count and unresolved passage correction (2026-10-30)

Follow-up: compiler version 6 centers the odd extra hole on the usable L-bracket
foot, between equal outer pairs. For five holes the four corner positions remain
the same as the four-hole pattern and the fifth is at their centroid. Minimum
2 mm inter-bore ligament clearance still applies, and validation separately checks
the center and mirror symmetry. The version-5 three-on-one-side/two-on-the-other
pattern remains reproducible for old exports. The change is limited to continuous
L-bracket feet: centering holes in the middle of plates or split supports could
conflict with the source mounting region or miss stock altogether.
The centered-hole follow-up passed 30 structure/passage/base-pattern tests plus
16 clearance/fastener tests. These include reopened STEP probes at all five hole
centers, unchanged corner positions, rejection of inadequate center spacing,
and a negative symmetry check against the old 3+2 pattern. The user's saved
version-5 five-hole plan also recompiles exactly using its historical compiler.
The app's live conversation regenerated the user's five-hole project as revision
`f682b8fd35e8`, parent `3a0f95acee6a`. Its five 3.4 mm base bores reopen as through
holes in STEP. The center is X=0, Z=-19.147627 mm in the attachment frame, exactly
the corner centroid. Independent STEP intersections report zero obstruction in
all five bores and the full cable passage. All non-base-hole operations are equal
to the prior revision, including the ribs and through cable cut. The saved proof
is `artifacts/prove_centered_fifth_hole.py`; the source and private exports remain
excluded from submission packaging.

The reported new motor project contained “four M3 base screws” only in its purpose
text. The L-bracket compiler always cut two base holes, and the old build summary
called the four **part** bores “mounting holes,” obscuring the distinction. The
wire-through request was also only access text with an empty `rear_passages` list.
These were real omissions; they were not a STEP export or tessellation defect.

Version 5 adds `bench_hole_count` as a positive integer with no design-specific
count cap. Deterministic placement distributes any requested count across two
L-bracket lanes or the available plate/rail/bridge lands. Four L-bracket holes
form a rectangle. Unspecified L base depth expands to preserve 2 mm bore-to-edge,
wall/rib and inter-bore ligaments. Explicit dimensions are never enlarged silently.
The existing 256-operation, 2,000 mm workspace limits still bound computation;
requests exceeding them fail before execution. Each independent foot/rail needs
at least one fastener, without claiming that one fastener restrains rotation.
The validator compares the total against the requirement, samples actual native
bore walls/axes through each foot and checks edge distances. Summaries and metrics
report part and base counts separately. Version 1–4 outputs remain reproducible.

`through_access_required` records intent even while a measured profile is
unresolved. Both readiness and compilation block an unresolved requested passage;
accepted concept assumptions do not bypass that guard. Profile choice remains a
semantic decision from the conversation, not an invented automatic cable detector.
The existing full-depth native intersection check remains independent of emitted
cut records. Historical access prose is not silently reinterpreted on load.
The current user's lower recess is identified from their earlier description and
image; no motor-specific profile ID or hole count is embedded in application code.

Verification: `pytest -q --disable-warnings --junitxml=demo/test-results.xml`
passed **107 tests in 108.01 seconds**. Counts 1, 3, 4, 7 and 20 were exercised on
L-brackets; plate, rail and bridge counts were also exercised. Regression checks
reject missing native bores, count mismatches and unresolved through requests,
preserve the last valid revision on dimension conflicts, enforce count locks and
reproduce legacy version-4 plans. A preceding full run hit a transient Windows
temporary-directory cleanup error in unchanged STEP intake; its focused rerun and
the final full run passed. No intake behavior was changed to hide the failure.

The live ChatGPT-subscription app conversation revised private project
`4d38ff99365543ca9b6ebff394457046`, creating revision `98f3eae93f20` from
`938f85c8e86f`. The AI captured count=4 and the lower through profile, generated
the unreinforced L-bracket and accepted the supported geometric checks. The app
prepared STEP; independent OCP probes found zero intersection through all four
3.4 mm base bores, solid material beside each bore, and zero intersection with the
complete through-passage profile. The STEP is one valid solid and the motor pattern
and cable outline are unchanged. The private proof script/report and export are
kept under artifacts and excluded from the public submission.

## Architecture and decisions

| Module | Responsibility |
| --- | --- |
| `app.py`, `controls.py`, `viewer.py` | Streamlit interaction, Plotly assembly/evidence, parameter controls and history. |
| `picking.py`, `hole_picker.py`, `hole_picker.js` | Validated measured-hole selection, a small Streamlit component and WebGL mouse events. |
| `intake.py` | CadQuery/OCP STEP import, declared units, source bodies, meshes, trimmed planes, circular boundaries, coaxial inward cylinders, contact samples and attachment frames. |
| `contracts.py` | Frozen Pydantic records, explicit millimeters, provenance, bounded plans and dependency/reference validation. |
| `manufacturing.py` | Material guidance, atomic manufacturing edits and export record; UI controls remain in `controls.py`. |
| `agent.py`, `subscription.py` | Schema-constrained decisions, focused questions and requirement edits using one model per turn. |
| `planning.py`, `retention.py` | Deterministic plan compilation, measured references, placements, supported fixture compositions, locating trays/strap slots, surrounding attachment and access cuts. |
| `executor.py` | All generated fixture solids, booleans, tessellation and USD BRep I/O in NVIDIA SMLib. |
| `validation.py` | Individual, method-specific geometry checks. |
| `project.py` | Candidate builds, last-valid preservation, immutable revision records, local snapshots, restore and ZIP export. |

CadQuery is deliberately reused as the STEP importer and measurement layer.
It constructs synthetic **source test specimens only**, never fixture bodies.
Source BReps are not converted into SMLib; plain numeric measurements and meshes
cross the boundary. No converter build, second OpenUSD runtime, microservice,
database, frontend framework or multi-agent framework was introduced.

The mouse picker is a small inline Streamlit v2 component, not a separate frontend
service. Plotly is served locally from the pinned Python wheel. All candidate
holes are drawn in the original source pose from their measured interface frames.
Plotly's WebGL hover hit test plus a real pointer release identifies a hole;
pointer movement suppresses selection while orbiting. A short delay allows the
hit test to settle after fast pointer motion. The camera is retained across picks.
Plotly's cloud-sharing control is removed from this component.

Browser events contain only a draft context and measured interface/hole IDs.
Python rejects stale events, unknown IDs, extra fields and mixed-face selections.
An explicit stationary-face checkbox and Apply action record user provenance and
persist the selected subset. Empty drafts cannot silently become all holes.
The usual lock checks and last-valid revision behavior still apply.
References: [Streamlit components](https://docs.streamlit.io/develop/api-reference/custom-components/st.components.v2.component)
and [Plotly events](https://plotly.com/javascript/plotlyjs-events/).

The two kernels passed in one Python 3.12.10 process on Windows x64. A lock
serializes SMLib work across Streamlit sessions. Native process isolation was not
needed for the exercised cases; an access violation can still terminate the app.
The dependency proof creates a 40 x 30 x 8 mm SMLib box and subtracts a radius-2
through cylinder. Volume before/after USD round trip: 9499.469066 mm³, valid
manifold topology. NVIDIA's wheel emits missing `pxr.*` Python-module warnings
during USD loading despite successful native I/O. Installing another `usd-core`
is not the fix; the wheel's bundled runtime is retained.

## Planner integration and the subscription adjustment

At the user's request, the default live route uses the installed **Codex CLI with
ChatGPT sign-in**, avoiding Platform API credits. CLI 0.165.0-alpha.1.2 reported
“Logged in using ChatGPT.” Its supported `exec --output-schema` interface returned
validated design actions in an actual three-turn generation/revision run.
This is a cloud model reached through a local CLI, not local model inference and
not automation of the desktop chat window. Subscription usage still counts.

The adapter uses argument arrays and stdin, an isolated temporary working folder,
read-only sandbox, ephemeral sessions, ignored user config, and disabled shell,
apps, plugins, browser/computer, code-mode, hooks and multi-agent capabilities.
It removes API-key environment variables and requires ChatGPT authentication.
No auth token is read or copied by application code. No global config is edited.
`FIXTURE_CODEX_PATH` and `FIXTURE_CODEX_MODEL` are optional; absent a model override,
the CLI uses its own default. Each call times out after 120 seconds. A separate
OpenAI SDK Responses backend uses `OPENAI_API_KEY`, `OPENAI_MODEL` (gpt-6-astra
default), a 45-second timeout and zero hidden retries; live API-key use is untested.

The API route calls a strict `design_action` function; the subscription route
returns the same action schema as constrained JSON. The controller compiles it
into the numeric fixture plan, rather than asking the model to invent CAD
coordinates. This is an architectural adjustment from literal tool calling on
every transport; it preserves the same bounded application actions and checks.
Actions support clarification, highlighting, proposals, build, inspection and
revision. Source metadata is data. Unknown operations, references, dimensions,
NaN/infinity and invalid dependencies are rejected before native construction.
There is no `eval`, model-generated shell or Python, or formula evaluation.

Model-derived edits are labeled AI provenance; explicit UI and offline command
edits are user provenance. Source dimensions remain measured; placement and stock
extents are derived. Default 6 mm thickness, 8 mm margin and 12 mm gap are visible
concept assumptions requiring acceptance. Nominal fastener, modeled diameter,
material, loads and engagement remain separate fields. Unknown is accepted.
The conversation log plus requirements snapshot preserves supporting context.

No unbounded repair loop exists. Tessellation gets at most one retry with a
tighter chord/angle tolerance; it never changes CAD parameters or locked values.
Other failures return to the current valid revision or a recoverable proposal.

## Geometry and validation scope

The attachment frame's Z points inward; the fixture lies at Z <= 0. Projected
source bounds determine pitch and stock extents. A geometric candidate is
automatically chosen only when one sampled-contact interface has all source mesh
vertices on its inward side. Stationary meaning still requires user confirmation.
Symmetric plate faces remain ambiguous and require selection.

Closed circular inner wires exclude external bosses and mixed slot boundaries.
Split arcs on one circle and coaxial inward cylindrical faces are grouped.
The smallest coaxial bore is retained; chamfers/counterbores with complex topology
still need manual review. Hole subsets can exclude ports, and corrections appear
in the requirement/revision record. Arbitrary coordinate edits are not offered.

Contact evidence retains trimmed outer/inner boundaries and samples annuli at
96 points per source hole. Native support rings are sampled separately. This is
not a proof of full footprint containment. The tool refuses unsupported contact
or source protrusions behind the mounting plane instead of claiming fit.

Plate and rail plans use the same operations. Rails are merged overlapping
support bands around measured hole rows; a usable gap must remain. Each rail is
an intended separate body requiring its own clamp/bench attachment. Lower-level
stock, cylindrical bosses, connected supports, unions/differences and slots are
implemented; the planner UI exposes the two verified compositions and finite box
access cuts rather than an arbitrary CAD language.

Limits: 30 MB STEP, up to 16 selected source bodies, 24 instances, 256 operations,
64 concurrent generated bodies, 2000 mm operation extents/coordinates. Small
edge distance default: 2 mm. These are prototype limits, not fabrication standards.
An operation-count limit can reject complex 24-instance patterns.

Checks distinguish passed / failed / inconclusive / not evaluated:

- STEP declarations and explicit source/attachment confirmation.
- Expected hole count and actual SMLib bore wall samples at three depths and
  twelve angles, with axis-to-wall distances. Position tolerance: 0.01 mm.
- Retained contact rings; stock side edge distance; compiled width, gap and thickness.
- Source-instance conservative bounding-box separation; overlap is inconclusive.
- SMLib intersection against finite user-defined box volumes for **fixture**
  obstruction. Text-only access is not evaluated; source obstruction is not tested.
- Native manifold checks, positive volume, one connected solid per intended body.
- Export/reopen body count, topology, bounds within 0.01 mm and volumes within 0.1%.

Bench equipment is not imported; clamp/bolt attachment is inconclusive as a full
assembly relationship. Exact source-to-fixture collision, strength, thermal,
fatigue, vibration, speed and complete manufacturability are not evaluated.
Source preview meshes are explicitly not converted source BReps.

## Reused components and provenance

Installed packages are unmodified. `requirements.lock` pins the full resolved
environment; the principal versions and roles are below. Package notices remain
in their installed distributions; this project does not redistribute the wheels.

| Component | Version | License / role |
| --- | --- | --- |
| [usd-brep / SMLib](https://github.com/NVIDIA-Omniverse/usd-brep) | 1.0.1 | Wheel metadata: Apache-2.0 AND LicenseRef-TOST-1.0 AND BSD-2-Clause AND BSD-3-Clause AND MIT AND BSL-1.0. Native fixture kernel and BRep USD. Read bundled notices for components. |
| [CadQuery](https://cadquery.readthedocs.io/en/latest/importexport.html) | 2.8.0 | Apache-2.0; source STEP import/inspection and synthetic source specimen generation. |
| [cadquery-ocp](https://pypi.org/project/cadquery-ocp/) | 7.9.3.1.1 | Wrapper wheel metadata Apache-2.0; includes OpenCASCADE components with upstream notices. |
| [Streamlit](https://docs.streamlit.io/) | 1.66.1 | Apache-2.0; local UI and AppTest. |
| [Plotly](https://plotly.com/python/) | 7.1.0 | MIT; 3D preview and standalone HTML. |
| [Pydantic](https://docs.pydantic.dev/) | 2.14.2 | MIT; strict record validation. |
| [OpenAI Python](https://github.com/openai/openai-python) | 3.41.0 | Apache-2.0; optional Responses API backend. |
| NumPy | 2.5.4 | Wheel lists BSD-3-Clause and bundled permissive notices; coordinate math. |
| pytest | 9.2.0 | MIT; regression tests. |
| Ruff | 0.17.3 | Development-only formatting/linting; not required by runtime lockfile. |

All bundled STEP files were generated for this project, with known reference
dimensions and CC BY 4.0 redistribution permission recorded in
[samples/PROVENANCE.md](samples/PROVENANCE.md). No manufacturer sample or external
CAD code was copied. API usage follows the installed type stubs and official
documentation; project-specific algorithms and tests were written for this task.

Development used Codex with **GPT-6 Astra**, shell tools, official documentation,
and browser inspection. AI assisted implementation, test construction, debugging
and documentation. Actual native kernel assertions, independent analytic volume
calculations, transformed STEP tests, UI tests and clean reinstallation checked
the outputs. The development model is distinct from the application's CLI-selected
runtime model. No development subagents were used.

## Verification and completion status

Run `python -m pytest -q` in the pinned environment. The verification record covers
known source dimensions, unrelated three-hole pattern, rigid transforms, body
selection, ambiguous and unsupported cases, native preview volume, two
compositions, quantities/layouts, surrounding bolt holes, real access cuts,
preserved locks, API/schema/kernel failures, export/reopen and UI restore.
Additional tests cover subscription login enforcement, removal of API keys,
disabled execution and timeout behavior. Live calls are explicit opt-in scripts.

The initial clean-environment suite passed **25 tests in 22.04 seconds**. See
`demo/verification.txt` and `demo/test-results.xml` for the actual final output.
Windows sandbox socket restrictions blocked AppTest until it ran with local
loopback permitted; this was not a Streamlit application defect. A native mesh
decoder defect found by the access-cut test was fixed: SMLib emits count-prefixed
polygon indices, not a flat triangle list. An independent mesh-volume test guards it.

Fresh `.venv-clean` installed from the lockfile, `pip check` passed, both-kernel
proof passed, and exported fixture reconstruction matched 38358.615110 mm³.
The real subscription sequence generated a plate at 109014.515792 mm³ and four
rails at 38358.615110 mm³, keeping six instances and 24 measured mounting holes.
Its action record and export are in `demo/`.

Stages 1–7 operate end to end, including live subscription planning. Stage 8's
regression core is implemented and has expanded to the supplied motor and IEC
connector, L-brackets/bridges, STEP transfer and hole-free trays as recorded above
and in the dated follow-ups. Stage 9 includes setup, pinned packages, source samples,
documentation, demo scripts/exports, public GitHub publication and the user-reported
cumulative hours. The continuous screen recording remains incomplete; no recording
link is fabricated.

## Remaining work, in priority order

1. Add direct 3D selection of openings and keep-clear areas, with measured references
   and native obstruction checks. This is the next suggested product improvement;
   the motor L-bracket and its through cable passage are already implemented.
2. Record the 2–3 minute real-motor workflow using the now-working subscription
   backend. The [demo guide](demo/DEMO.md) and live-call record support preparation.
3. Expand chamfer/segmentation and curved-contact regressions; replace sampled
   contact with stronger trimmed-face containment and add finite source access checks.
4. Add native-worker isolation/timeouts before accepting untrusted large CAD in a
   service, and expand fabrication constraints only with representative tests.
5. Add custom rail orientations and more layout/attachment choices, exact source
   collision bridging, and engineering analysis as explicitly separate capabilities.

**Historical partial time measurement:** implementation and verification interval:
17:03:20–17:38:04 PDT on October 29, 2026, **34 minutes 44 seconds (0.579 hours)**
of elapsed agent wall time, including dependency installation and waiting.
This excludes the brief initial inspection before the first clock reading,
earlier planning, final packaging and unrecorded human effort. The current
user-reported cumulative total is **3 hours 30 minutes**, recorded at the top of
this document; this partial interval is not an additional amount to add to it.

## Mouse selection follow-up

Added measured-hole mouse selection without changing source geometry or the
SMLib executor. Regression cases exercise single/multiple picks, deselection,
mixed faces, stale events, extra event fields, invalid IDs, requirement locks,
stationary confirmation, empty drafts and save/reload. Marker positions and
radii are checked on the motor specimen, unrelated sensor specimen and rotated/
translated specimen. A two-hole selection generates two actual SMLib cuts and
passes native validation. Streamlit AppTest exercises Apply and Clear behavior.

Browser verification exercised real pointer clicks on the synthetic specimen,
rotation without changing picks, camera retention, mixed-face rejection and
applying two selected rear holes. No AI call is required for mouse selection.
The complete updated suite passed **31 tests in 24.12 seconds** on the existing
`.venv` (Python 3.12.10); Ruff's undefined/unused-name checks passed. The original
clean-install verification remains separate. Results are saved in
`demo/verification.txt` and `demo/test-results.xml`.
This follow-up's elapsed development time was not separately clocked and is not
included in the original time accounting above.

## Manufacturing follow-up

Added a dedicated Manufacturing panel with FDM/FFF, machined stock and custom
processes. Filament choices are PLA, PETG, ABS, ASA, Nylon (PA), PC, TPU, PETG-CF
and PA-CF, plus unknown/custom. Short descriptive guidance links to primary
[Prusa material documentation](https://help.prusa3d.com/category/material-guide_220),
including its [composites guide](https://help.prusa3d.com/article/composite-materials-filled-with-carbon-kevlar-or-glass_167387).
No numerical material properties, safety factors or temperature presets were
copied or inferred; the user supplies the exact grade and printer profile.

The existing fabrication/material fields remain compatible with saved projects.
An additive frozen `PrintSettings` record defaults every field to unspecified.
It stores printer, grade, nozzle diameter, layer height, wall count, infill,
orientation, support preference and notes. Prototype input bounds are 0.1–2 mm
nozzle, 0.02–1.5 mm layers, 1–30 walls and 0–100% infill; layer height cannot
exceed a specified nozzle diameter. These bounds detect input errors, not printer
compatibility. Zero infill remains distinct from unknown. UI drafts apply only
on Save, and changing away from FDM in the panel clears its saved print settings.

The bounded conversation schema accepts partial print-setting edits, merges
them with existing settings before validation, and preserves per-setting
provenance. Manufacturing edits use the same locks as other requirements and
are saved in the conversation and project record. Revisions retain their own
settings. Export includes `manufacturing.json` for the selected generated
revision; pending requirements cannot mislabel earlier CAD. Geometry remains
the existing SMLib plan: there is no automatic sizing by material, structural
analysis, slicer integration, print orientation transform, support geometry,
G-code or printer compatibility check.

The live planner returned a metadata-only `revise` action despite saying no build
was requested. The controller now treats manufacturing-only `revise` actions as
saved requirements, while explicit `build` and geometry revisions retain their
usual behavior. A UI regression covers this case so model phrasing cannot start
an unnecessary native build for a printing-settings edit.

Verification on the existing Python 3.12.10 environment: **41 tests passed in
27.94 seconds**, including native generation, manufacturing save/reload, legacy
records, revision restore, export isolation from drafts, partial conversation
edits, locks, invalid settings, unknowns, zero infill, custom material and process
switching. Ruff F checks passed. Browser verification selected PETG and saved
0.4 mm nozzle, 0.2 mm layers, four walls and 35% infill on a synthetic specimen.
The user's motor project was restored after restarting the local server; its
manufacturing requirements were not chosen by the developer.

A real subscription call using a synthetic specimen recorded a requested
0.4 mm nozzle and 35% infill while retaining 0.2 mm layers and four walls. The
action and resulting settings are in `demo/manufacturing-live-record.json`.
This used the existing ChatGPT subscription backend, not a Platform API key.
Development time for this follow-up was not separately clocked and is excluded
from the original time accounting.

## Hole-size display follow-up

Mouse-picking colors now identify measured bore sizes across all faces of the
immutable source analysis. Diameter labels use 0.001 mm display precision only;
source measurements and operation parameters are unchanged. Colors are assigned
in sorted diameter order and remain stable through selection, clearing and
switching faces. The eight base colors extend with distinct hues for larger size
sets. Selected holes retain their size color, with thicker rims and white diamond
centers, so selection does not hide diameter differences. Other faces are faded.
A labeled legend and hover values make the display usable without relying on
color alone. The assembled view uses the same colors, and list options include
measured diameters.

Colors do not infer nominal screw threads or assign clearance sizes. Mixed-size
selection shows the current compiler limitation: one confirmed fixture clearance
diameter applies to the whole selected mounting pattern. Per-hole fastener and
clearance overrides remain future work.

Added `mixed_hole_sizes.step`, original synthetic source geometry with two 3 mm
and two 5 mm bores on a mounting face. Regression verification checks its imported
measurements, source-pose marker positions, colors across faces and selections,
assembly legend, and selecting/applying/clearing a mixed-size subset in the UI.
The full suite passed **43 tests in 29.83 seconds**; Ruff F checks passed. No
dependency, native fixture executor or source-motor requirement changes were
needed. Browser clicks selected a 3 mm and a 5 mm opening on the synthetic
specimen; both kept their size colors and showed white diamond centers. The
mixed-size notice and selected diameter summary appeared. The motor project
remains open with its updated legend and no developer-selected mounting holes.
Elapsed development time was not separately clocked.

## 2026-10-30 — through passages, preview shading and concise design choices

The motor's lower shaped recess was a measured protrusion relief, only
2.167096834 mm deep in a 6 mm wall. It was therefore correctly exported as a
blind pocket but did not satisfy wire exit access. New `rear_passages` requirements
reference selected measured rear-profile IDs. Version-4 compilation preserves the
profile's XY outline and extends its cut beyond the complete fixture's stock and
support Z extents. Unselected pockets retain their measured depth. There is no
motor-specific shape, dimension or cable classification in this logic. The AI sees
measured centers/extents and can choose a profile from a user location description;
the UI also offers an explicit selector. Ambiguous descriptions still require a
choice. No connector fit or cable bend-radius check is implied.

Native validation independently reconstructs the requested full-depth tool and
intersects it with the final fixture, failing above 0.01 mm³ or on a kernel error.
This detects a blind pocket even when that pocket's own clearance check passes.
Contact protection, base-hole checks, single-solid connectivity and export checks
remain active. Depth derives again when stock thickness changes. Quantity changes
repeat the same selected passage per source instance. Interface changes clear
stale profile choices; locks are enforced. Legacy compiler versions 1–3 remain
available for reproduction of historical inputs.

The apparent triangular dents in the app were caused by smoothing across shared
wall, bore and rib vertices. `fixture/render_mesh.py` splits only the shading
indices at dihedral angles above 30 degrees. Coplanar triangles keep consistent
normals, cylinder segments remain smooth, and every triangle coordinate is
unchanged. The display transformation also works on older saved meshes. An
eight-entry identity cache avoids rebuilding this topology on every UI rerun.
The STEP writer and native CAD do not use the display transformation.

Mounting proposals now add an open/ribbed L-bracket alternative and raised
L-bracket/bridge variants. Raised variants add two stock thicknesses to a derived
height and are not offered for an explicit/locked height. Each candidate is
compiled with its actual variant requirements; infeasible or locked choices are
omitted. Displayed dimensions and generated requirements come from the same
candidate. This expands choices within the existing four supported construction
families rather than claiming unrestricted geometry synthesis. Selected mounting
holes, fasteners and passage requirements carry through to every proposal.

Proposal cards show a short tradeoff and dimensions. Design details, validation
and full AI feedback are collapsed. Planner explanations request at most 45 words;
review summaries request at most 35. Full structured findings remain saved/exported
but are no longer duplicated into the conversation. Historical long replies show
a short excerpt with Read full response. Buttons use human names (Generate
L-bracket, rather than an internal composition identifier).

`hole_fasteners` assigns a nominal and optional custom clearance to selected
measured hole IDs. The UI groups equal measured diameters and offers a proposed
metric size, the nearest smaller numbered-inch size, Other and automatic/blank.
A 3 mm group offers M3 and #4. No thread identity is inferred. Unknown sizes remain
assumptions; custom dimensions and existing global overrides are preserved. New
per-hole choices cannot bypass locked global nominal/clearance requirements.
Changing the mounting selection drops assignments for deselected holes.

Numbered-inch rows #0–#6/#8/#10/#12 use the same pinned
[Albany County Fasteners chart, page 1](https://www.albanycountyfasteners.com/media/6b/b8/g0/1764944339/clearance-hole-chart.pdf?ts=1764944339),
verified 2026-10-30. They are labeled ACF inch-series chart, not ISO 273. For #4,
normal clearance is 0.1285 inch, exactly 3.2639 mm using 25.4 mm/in. The fine,
medium and coarse controls map to the supplier's close, normal and loose columns.
Metric entries continue using the published ISO 273 table on page 2.

Verification: **95 tests passed in 92.81 seconds**, Ruff F checks passed. Added
tests cover native and reopened STEP through access, deliberately blind cuts,
thickness revisions, multiple instances, profile selection/locks, legacy plans,
distinct native proposal geometry, unchanged preview coordinates and crease
normals, cylindrical smoothing, mixed metric/inch choices, custom/blank choices,
lock bypass prevention and the readable/collapsed UI. Full source and native
geometry generation remain separate from display shading. Elapsed development
time for these follow-ups was not separately clocked.

Live app follow-up: the first AI revision attempted to highlight a newly exposed
rear profile and was rejected by the old source-feature-only highlight allowlist.
That validator now accepts only measured rear-profile IDs from the current
interface, with a regression rejecting nonexistent IDs. Profile highlights draw
an outline in normal viewing mode; only explicit Access volumes draws a filled
envelope, avoiding an apparent cap over an open passage. Targeted planner/workflow
checks passed (23 tests in 31.98 s), followed by passage/render/picking checks
(16 tests in 19.01 s, recorded in `demo/test-results-followup.xml`).

Through the live subscription conversation, project `66e1183e0a88447fb794bc4525596abe`
generated revision `cb916fffb510`, parent `1a0f3655df0f`. The AI selected the lower
measured profile and accepted the resulting geometry after native/visual review.
The only changed geometry operation is `rear-relief-0-0`; its XY origin and convex
outline are unchanged. Requirements differ only in passage selection/provenance.
The central recess, four motor bores, two base bores, overall dimensions, ribs and
explicit 3.2 mm clearances remain unchanged. The result is one solid with 68 faces.
Displayed native volume is 34,730.991353 mm³; adaptive native and reopened STEP
volumes are 34,730.904922993 and 34,730.904925182 mm³ respectively. Both the native
full-depth check and an independent Boolean intersection of the reopened STEP
with the exported passage tool report **0 mm³ obstruction**. The exported bundle
reproduced successfully at the displayed native volume. The revised source, STEP,
extra proof script/report and screenshots remain private under `artifacts/`.

## Selection reliability and simpler intake/manufacturing

This follow-up supersedes the material-library, machine and slicer UI described
in the earlier manufacturing history above. Manufacturing now asks only for the
method: 3D printing, machined stock, custom or unknown. The planner action schema
no longer accepts material or print-profile changes, and current planner
requirements omit those fields. Older saved projects and revisions still load
their historical records. The new manufacturing export contains the method and
concept guidance; the original requirements record remains backward compatible.
The historical `manufacturing-live-record.json` documents the earlier feature,
not the current input contract.

The method informs the conversation and proposal explanations: a connected
printing plate versus disconnected rails with separate base attachments, or
machining stock with straight cuts. Saving the method does not regenerate CAD.
No slicer, print orientation, support generation or strength analysis is added.
The bounded plate/rails executor and existing geometric checks remain unchanged.

STEP intake automatically groups every source solid into one application part,
preserving relative placements and source topology. The manual body selector
and its empty-selection error are removed. OpenCASCADE uses a compound rather
than forcing disconnected geometry into a falsely fused solid. The existing
16-solid input bound remains; larger files receive a clear whole-file rejection,
with no silently discarded pieces. Newly imported projects are saved immediately.

Hole picking now uses 20-pixel center targets and additive, cumulative batches.
Repeated clicks, duplicate events and reordered additions cannot toggle holes
off. Local feedback is immediate, pending additions survive component rerenders,
and the server validates all measured IDs and their face as one batch. After the
first pick, other faces' selectors are hidden. Dragging, cancelled gestures and
delayed hover after pointer movement do not add holes. Explicit removal uses
the selected-hole list's × buttons and creates a new context, invalidating old
in-flight additions. Clear and Apply retain their existing confirmation and
requirement-lock behavior. Diameter colors still describe measured bores, with
one shared fixture-clearance setting in the current compiler.

Verification on the existing environment: **38 tests passed in 33.06 seconds**,
including native geometry, whole-file multi-body intake, method-only controls,
legacy loading, revision/export isolation, additive selection and explicit
removal. A Node.js harness executes the actual picker JavaScript with a minimal
DOM/Plotly adapter; its three pointer and rerender tests passed and are included
through one pytest wrapper (skipped if Node.js is unavailable). Ruff F checks
passed. Updated results are in `demo/verification.txt` and `demo/test-results.xml`.

Live browser verification on `mixed_hole_sizes.step` selected 3 mm and 5 mm
holes, repeated a click without removing it, rotated from a selected target
without changing the count, and removed one hole explicitly while retaining the
other. Saving 3D printing showed only the method control. The local server was
restarted to discard stale cached modules. The user's motor project and its
conversation were resumed; synthetic verification did not change its requirements.
This follow-up's elapsed development time was not separately clocked.

## Start design and bounded AI feedback

Added an explicit Start design entry point and brief field. It sends the saved
measurements, manufacturing method, selected mounting pattern and conversation
to the chosen planner. Start always stops at clarification/proposal, even if a
model prematurely requests a build. Users answer in chat and choose Generate
after reviewing the proposal. Missing required facts block generation in the
controller. The advanced requirements/assumptions panel is collapsed by default;
concept dimensions and assumption acceptance remain visible beside proposals.

This remains a reusable fixture tool. No new motor, quantity or L-bracket
templates were introduced. A shared capability description explicitly separates
the currently supported plate/rail compiler from the broader primitive executor.
An unsupported planner action explains a missing capability without applying
substitute requirements. Additional fixture structures require real compiler and
validation work; the model cannot invent their implementation.

All UI generation paths now run generate/check/review through a separate
controller. Successful builds are reviewed with their requirements, operation
plan, measured checks and three headless views of actual meshes (assembly,
fixture underside and side). Matplotlib 3.11.2, already in the lockfile, renders
these with the Agg backend. Large display meshes may be decimated; numeric CAD
checks, not pixels, remain the measurement evidence. Failed builds supply their
own error/partial plan/checks without images of the previous valid revision.

The schema-validated reviewer can accept the geometric concept, request user
input, or propose one correction. Automatic changes are restricted to gap,
margin and thickness, only when unlocked and default/AI-assumed. Dimensions
extracted from a user's conversation are now conservatively marked user-supplied
and cannot be changed by the reviewer. Quantity, mounting features, clearances,
load statements, access envelopes, fabrication and width limits cannot be relaxed
by this loop. After one correction, a second build/review ends the run; no rerun
or recursive model action can trigger another correction. The controller rejects
an AI accept verdict on a failed build. Model/native failures retain the last
valid geometry and label incomplete review explicitly.

Feedback records persist with the project and identify each attempted build and
its resulting revision. Exports include only feedback for the selected revision
in `ai-feedback.json`, plus `review.png` when available. Old projects still load
with an empty feedback history. Offline mode never simulates AI feedback. A page
refresh does not repeat a call or build; each run requires a button/chat event.

The subscription adapter uses the installed CLI's `--image` and strict output
schema while keeping execution tools disabled and API keys removed. The optional
API adapter uses image inputs and a dedicated structured review tool. References:
[CLI developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
and [Responses image inputs](https://developers.openai.com/api/docs/guides/images-vision).
No dependency or authentication architecture change was needed.

Verification: **49 tests passed in 45.96 seconds**, and Ruff F checks passed.
Tests exercise Start/clarify/propose/generate/review in Streamlit, collapsed
advanced controls, rerun idempotence, two unrelated source parts, actual rendered
views, one successful repair of an overly wide plate, repair limits, protected
dimensions, failed checks, rejected false acceptance, timeout recovery, image
payloads for both adapters, save/load and revision-specific export. External model
responses in regression tests are explicit doubles; native CAD is real.
Browser verification confirmed the live review record and collapsed advanced
panel. It also exposed a saved-project selector reset when new project files
changed the option list. An explicit widget key now preserves the chosen path;
a regression adds another project between selection and Resume to verify it.

The opt-in `scripts/prove_feedback.py` also completed real subscription planning,
SMLib generation and image-backed review for two synthetic sensor brackets. It
produced one 152 × 58 × 6 mm plate with six 4.5 mm holes and approximately
52,323.462 mm³ volume. The real reviewer accepted the geometric concept while
retaining unassessed operating/access conditions and inconclusive clamp attachment.
The record and export are `demo/live-feedback-record.json` and
`demo/live-feedback-export.zip`. No live Platform API-key request was made.
Elapsed development time for this follow-up was not separately clocked.

## 2026-10-30 — perpendicular structures and a quieter selection workflow

The capability boundary now includes four reusable structures: plate, rails,
L-bracket and bridge. No dimensions, count, pattern or mounting decision from the
D3536 motor are embedded in the compiler. A common registry supplies names and
descriptions to proposals, controls and AI capability records. Unsupported nests,
articulated clamps and arbitrary-angle/freeform synthesis remain explicit limits.

The installed NVIDIA API was checked against its Python type stubs and the
[upstream project](https://github.com/NVIDIA-Omniverse/usd-brep). The independent
`scripts/prove_structures.py` proof exercised a capped triangular linear sweep,
union into a wall/foot, a cylinder rotated 90 degrees, a real base-hole cut, and
USD BRep round-trip. Tight numerical volume comparisons use `volume(1e-7)` in
that proof: the native default relative accuracy is 0.001 and initially produced
a 0.066 mm³ difference in a 113.097 mm³ cut. This was numerical integration
tolerance, not a failed rotation. Native geometry construction remains SMLib-only.

Implementation choices:

- The selected interface stays in XY at Z=0. L-brackets grow a wall upward along
  Y and a perpendicular foot rearward along -Z. `mount_height` measures from the
  base top to the interface origin, and `base_depth` is the rearward extent.
  Optional triangular side ribs fuse into the same solid. Base bores run along
  Y; source mounting bores remain along Z. USD declares Y-up and previews agree.
- Bridges place two side legs outside the source envelope and add outboard feet,
  keeping an open span under the mounting platform. Height measures interface
  plane to base top along Z. The maximum-width constraint includes both feet.
- Missing heights/depths are derived concept dimensions displayed on each
  proposal. User overrides and locks persist through revisions. No thrust,
  bending, fatigue, print strength or propeller-position assumptions are made.
- Rear protrusions are handled only for the new structures: clip source mesh
  triangles behind the interface and pad their bounding box by 0.3 mm (twice
  the intake chord tolerance). The actual fixture receives a box cut. If that
  box removes a sampled mounting contact annulus, compilation rejects it.
  Native box-intersection checks accompany the result. Exact cross-kernel source
  collision remains not_evaluated; the mesh box is an approximation.
- A new-structure clearance bore may exceed the modeled opening only if at least
  1 mm remains to the sampled outer contact radius. This separates fixture
  clearance from an M3-style thread callout without guessing thread geometry.
- New native checks sample base bore walls and axes at three depths and verify
  base-hole count and edge distances. A regression deliberately omits base cuts;
  validation detects the solid material where a void was required. Existing
  contact, alignment, dimensional, connectivity and round-trip checks still run.
- Plate/rail operation records stay deterministic. Existing version-1 records
  load new optional fields with defaults. The prior `demo/example-export.zip`
  still recompiles and rebuilds its four rails (38,358.615110 mm³).

UI changes group hole selection, manufacturing method and collapsed advanced
controls under **Design choices**. The technical candidate selector is now
**Advanced — mounting evidence**, closed by default. **Finite access region**
became **Clearance volumes (optional)** inside the collapsed requirements section:
it is for wire/tool/motion keepouts, not a mandatory setup step. Viewing toggles
are in a collapsed View options section. Streamlit's toolbar uses minimal mode,
and the Deploy button is explicitly hidden. Materials and slicer settings remain
absent from the active UI and AI inputs.

Selection latency had three avoidable sources: rebuilding/serializing the full
STEP figure on every click, rerunning the entire app (including proposals and
exports), and issuing a Plotly restyle for every detected hole. The picker now
runs in a Streamlit fragment, caches immutable figure JSON, retains an unchanged
component seed across additions, and batches all marker edits into one redraw.
Explicit removal/reset changes the context, invalidating in-flight clicks.
Repeated/coalesced additions remain idempotent. Pointer tests verify one redraw
per actual addition; UI tests verify that component data stays identical during
additions and changes on removal.

`scripts/profile_picker.py` on the saved motor analysis measured median Python
figure work of **245.211 ms uncached versus 1.343 ms cached**, five iterations.
This excludes first load, network transfer, GPU drawing and end-to-end click
latency; it is not a claim of a 183x total UI speedup. Browser verification on
the actual motor added two draft holes, repeated a click without deselecting,
retained the zoom/camera, and cleared the draft without applying a mounting
decision. Manufacturing was visibly below the hole controls, both Advanced
panels were collapsed, and Deploy was absent. Proof: `artifacts/ui-cleanup.png`.

The opt-in live proof `scripts/prove_feedback.py --structure l_bracket` used the
unrelated synthetic sensor part. The real subscription planner selected an
L-bracket for two parts with explicitly supplied 70 mm height and 40 mm base
depth, then native generation produced one connected body, six 4.5 mm mounting
holes and **142,406.591458 mm³** volume. Real AI review of generated views returned
accept while retaining unassessed strength/access and inconclusive bench clamp
compatibility. Its export reproduced successfully. Records are in
`demo/live-l_bracket-record.json` and `demo/live-l_bracket-export.zip`.

The actual motor project was resumed through the app and Start design was used
with its saved conversation. The app now proposes an executable ribbed L-bracket
and asks for the confirmed rear holes, manufacturing method, motor/base clearance
diameters and axis-to-base/finite clearance choices. Those answers were not
invented or copied from synthetic tests. No completed motor CAD or validated
bidirectional thrust capacity is claimed. Private STEP data stays outside the
submission archive. No API-key-backed live call was used.

Final verification: **60 tests passed in 54.77 seconds**; Ruff F checks passed.
Coverage includes the new structures on original, unrelated and transformed STEP
parts, rear relief, perpendicular base holes, connected ribs, grid placement,
limits/locks, wire openings, missing-hole detection, export reproduction and a
Streamlit L-bracket-to-bridge revision. Live subscription calls are separate from
the regression suite. Elapsed development time was not separately clocked.

## 2026-10-30 — separate measured rear clearances

The former single rear box rejected the user's confirmed motor pattern because
it filled empty space between separate protrusions and intersected contact around
f13-h5. The enhanced compiler instead clips the source mesh behind the selected
mounting plane, welds coincident seam vertices for adjacency only, and groups
connected rear patches. Original measured coordinates are retained. Each patch
gets an enclosing cylinder when its projected footprint is close to circular,
or an enclosing convex XY polygon swept along Z. The fixture is cut using native
SMLib cylinders or capped linear sweeps. This logic uses measured geometry, with
no motor dimensions, hole IDs or part-specific decisions embedded in it.

The implementation bounds each source to 32 rear regions and each profile to 48
vertices. Larger convex hulls use 48 supporting half-planes enclosing every hull
point, rather than removing vertices and shrinking the envelope. Region ordering
is deterministic, and the existing 256-operation limit still applies. A bounded
cache retains immutable source meshes and includes the complete interface frame
and padding in its key, avoiding repeated mesh analysis on UI reruns.

`rear_clearance` is a lockable requirement from 0.3 to 10 mm. The default/minimum
is twice the 0.15 mm intake mesh chord tolerance. Increasing it creates a normal
revision; automatic AI repairs cannot lower it. Cuts are checked against every
selected mounting contact patch before construction. Real conflicts still fail
with an explanation that another interface or a stand-off design is needed.
Stand-off synthesis, concave profiles and depth-varying reliefs are not implemented.
Convex envelopes can still overcut a complex connected patch; the system does not
discard geometry or weaken a mounting patch to make such a case pass.

Native validation checks that every expected envelope is present in every source
placement and intersects the final fixture by less than 0.01 mm³. Deliberately
omitted operations and uncut native bodies fail regression checks. Sampled contact,
bore geometry, connectivity and USD reopening checks continue to run. These are
mesh-envelope checks, not exact source BRep collision or structural validation.
Clearance for wires, tools and a future propeller remains separately specified.

Version-2 L-bracket/bridge plans contain the new profiles and padding. The
reproduction script selects the compiler by the saved plan version, preserving
version-1 L-bracket and plate/rail exports. The UI explains the count/padding on
proposals, exposes the padding inside Advanced, and shows purple measured rear
envelopes under View options → Access volumes. AI capability descriptions and
review context distinguish these measured reliefs from unspecified access space.

Verification: **67 tests passed in 63.70 seconds**, with Ruff F checks passing.
The new cases cover separate shaft/corner protrusions on an unrelated synthetic
part, both cylinder and polygon cuts, padding revisions and locks, real contact
conflicts with last-valid recovery, envelope coverage, missing cuts, rigid
transforms, bounded convex profile validation, and old/new export reproduction.
The native polygon proof produced a manifold prism of 92 mm³. A final viewer
legend regression also passed with the native generation/export test (7.17 s).

The running app resumed saved motor project `6712921389994fc4b618bab880f466ab` and
generated revision `e152367144dd` using the existing user-confirmed interface,
four selected holes and 3.4 mm motor/base clearances. It produced one connected
reinforced L-bracket, two base bores, one cylindrical rear relief and one convex
48-vertex relief, at **35,026.207949 mm³**. Both rear-envelope intersections were
zero. Native geometry/contact/base/clearance/export checks passed, and the private
export rebuilt to the same volume. No user requirements were replaced with demo
dimensions. The old compiler reproduces the reported f13-h5 conflict on this
same saved input; the enhanced compiler clears it while preserving that pattern.

Real subscription AI review completed through the app and returned `needs_input`
for propeller-axis/plane placement and rear cable-opening dimensions. The current
derived mounting height is a geometric concept default; no 5-inch propeller fit,
250 g bidirectional thrust capacity, vibration performance, screw engagement or
print strength is claimed. Private export and UI proof remain under `artifacts/`,
outside the submission archive. No live API-key call was used. Elapsed development
time for this follow-up was not separately clocked.

## 2026-10-30 — recoverable Windows CAD save failures

The reported `SmApiUsdImportBreps SM_ERR (1001)` was traced to project
`66e1183e0a88447fb794bc4525596abe`, attempt `72b5ee4ffb61`. Its saved inputs use
3.2 mm motor/base clearance holes, superseding the separate earlier 3.4 mm demo
project. The server logged Windows access denied while USD renamed its temporary
export to `fixture.usda`. The destination was only 64 bytes: a USDA header with
stage metadata and no BRep. The leftover 88,942-byte temporary file imports as one
valid manifold body, volume 35,063.605481 mm³. The import error was downstream of
the failed file save, not evidence of a mounting/clearance conflict. A controlled
Windows file handle excluding delete sharing reproduced the native rename failure.
The log does not identify which process caused the original denial.

`fixture/cad_io.py` now exports copies of the same native bodies to unique staging
files, rejects missing/header-only output, writes stage metadata to a separate
file, and reopens the candidate in SMLib. Topology, solid count, body count, bounds
and volume must match before verified bytes are atomically published. Publication
also checks byte identity. At most three save attempts use fresh paths, with
100/200 ms delays; no geometry parameters change. The existing native kernel lock
still covers construction, serialization and validation. Temporary files are on
the destination filesystem so publication can remain atomic.

Persistent failures have a typed `cad_export` category in the saved feedback.
The application preserves existing valid revisions, skips AI review/automatic
dimensional repair for storage failures, and asks for a Generate retry. The error
banner now distinguishes an unchanged prior design from an attempt with no saved
CAD; it no longer always claims a last valid result exists or tells the user to
correct requirements for this error. Legacy feedback records remain readable.

Verification: **72 tests passed in 66.93 seconds**, Ruff F checks passed. Five new
tests cover silent header-only exports, native export exceptions, valid but
mismatching round trips, persistent failures preserving the previous revision and
skipping the AI call, and an actual Windows rename lock released on retry. The
existing complete CAD/UI/revision/export suite also passes.

After restarting the local server, the exact failed project was resumed through
the app and Generate L-bracket retried. Revision `1a0f3655df0f` now contains one
connected body with four 3.2 mm motor bores, two 3.2 mm base bores and two measured
rear reliefs. Geometry/contact/clearance/export checks passed. The saved input
requirements were compared unchanged after generation. The private export also
reproduced at 35,063.606055 mm³. Real subscription AI review confirmed the build
and retained `needs_input` for the requested approximately 8 mm cable opening and
propeller placement; no new cable opening or physical strength validation is
claimed. Diagnostic logs, the original failed files, export and UI proof remain
private under `artifacts/`. Elapsed development time was not separately clocked.

## 2026-10-30 — automatic fastener clearances and solid STEP export

New plans use ISO 273 medium clearance by default. The lookup in
`fixture/fasteners.py` pins the fine/medium/coarse columns from page 2 of the
[Albany County Fasteners metric clearance chart](https://www.albanycountyfasteners.com/media/6b/b8/g0/1764944339/clearance-hole-chart.pdf?ts=1764944339),
verified 2026-10-30. Supported nominal rows are documented in README; unsupported
threads require an explicit custom dimension rather than a fabricated metric lookup.
The app never downloads standards while generating. Routine clearance questions
and approvals were removed from the controller and AI instructions. Fit/overrides
remain in Advanced. The design choices area displays the selected policy and values.

A supplied nominal takes precedence; otherwise each selected measured opening
gets the largest supported nominal at or below its diameter plus 0.05 mm. This is
explicitly an assumption, not thread recognition. A modeled minor diameter may
therefore need a nominal override. Mixed-size patterns receive separate mounting
cuts. Base fasteners use the supplied base nominal, mounting nominal, or smallest
assumed mounting size. Existing explicit mounting/base clearances and locks persist.
No printer tolerance compensation or fit/strength certification is implied.

Version-3 plans retain per-feature diameters, nominal, fit, standard/source/date,
basis and provenance. Native validation verifies bore walls and compares actual
mount/base cut sizes with the independently resolved policy. A larger standard
bore may exceed the source opening but must retain 1 mm to its sampled contact
radius. Source geometry is unchanged. Old version-1/2 plans reproduce their exact
previous operations; new automatic choices do not rewrite historical revisions.

The requested STEP required a serialization bridge. The installed usd-brep wheel
offers native USD BRep I/O but no STEP writer. NVIDIA's source-only
[usd_to_occt converter](https://github.com/NVIDIA-Omniverse/usd-brep/tree/main/tools/usd_to_occt)
requires a separate build; no prebuilt converter, CMake or MSVC toolchain was
available. Instead `fixture/step_export.py` transfers the generated SMLib BRep's
analytic planes/cylinders, exact rational NURBS edges and shared topology into
the existing OpenCASCADE runtime and writes STEP. Its interpretation of BrepArray
orientations and knot tables follows NVIDIA's
[converter source](https://github.com/NVIDIA-Omniverse/usd-brep/tree/main/source/OCCT_BREP_EXPORT).
No second USD runtime or additional dependency was installed. All fixture modeling
operations remain SMLib; the compiler is not replayed through CadQuery.

This deliberately bounded reader handles generated, untransformed millimeter USD
stages, with no external references, and up to 64 arrays/solids per array, 4,096
faces and 16,384 edges per array (50 MB file cap). The supported surface vocabulary
covers the four current fixture families including rear cylinder/convex reliefs.
Unsupported geometry fails explicitly. OCCT reconstructs UV parameter curves from
the preserved 3D curves and performs bounded wire/seam repair (precision 0.00002 mm,
maximum tolerance 0.001 mm). No tessellation becomes export geometry. Before and
after STEP serialization, validity, solid/face count, bounds within 0.01 mm and
adaptive volume/area within max(0.01, 1e-5 relative) are checked against SMLib.
Files are staged and published only after reopening passes. Hashes of both native
CAD and STEP guard cache/download reuse. Failure preserves previous native CAD.

Prepare STEP download / Download STEP exports the selected revision's fixture
solids in millimeters, excluding the source part. Separate rails stay separate
solids. After preparation the existing ZIP also includes STEP and its verification
report; all ZIPs include the fastener record (empty for historical plans).

The current private motor revision `1a0f3655df0f` transfers to one valid solid with
69 faces, preserving its explicit 3.2 mm mounting/base bores and rear reliefs.
Adaptive native volume is 35,063.519624853 mm³; reopened STEP is
35,063.519627042 mm³. Native area is 13,795.541745346 mm² and STEP area is
13,795.541695559 mm². Default fixed quadrature gave a misleading several-mm³
difference during the spike; adaptive integration and five samples on each native
edge (maximum distance about 9.21e-12 mm) identified this as numerical integration,
not altered geometry. The displayed older metric uses the original native
quadrature. The cable opening and propeller clearance remain unresolved, and this
export does not add load validation.

Verification: **85 tests passed in 76.12 seconds**, Ruff F checks passed. Thirteen
new cases cover standard fits, default question suppression, mixed actual bores,
explicit overrides and locks, separate base sizes, unsupported sizes, versioned
reproduction, all four STEP fixture families including multiple solids and rear
prisms, cylindrical bore surfaces, cache reuse/corruption and failure retention.
The existing complete Streamlit test now prepares STEP and verifies its download
control. No new live AI call was needed for these deterministic changes. Private
motor data and reference-converter research remain outside the submission archive.
Elapsed development time was not separately clocked.

## Mounting face selection and connector panel cutouts (2026-10-30)

The design controls now have matching Select mounting face / Select mounting holes
buttons. Each opens a separate draft with explicit Apply and Cancel. Repeated clicks
preserve selection, orbit drags do not select, stale event contexts are rejected,
and requirement locks still apply. Face selection highlights the actual planar
patch, points toward the outside occupied by the fixture, and offers its measured
holes for confirmation. Selecting another face clears old face-relative passage
choices and access boxes instead of silently reusing coordinates in a new frame.

New imports retain exact per-face trimmed tessellation. Older projects use existing
source triangles on the measured plane and within its trim bounds for display only;
coplanar overlapping parts can remain ambiguous, so the measured-face list is also
available. Picking is limited to supported planar interfaces with circular holes.
The browser ray-tests the displayed triangles, including the source as an occluder;
Plotly's nearest-vertex hover can otherwise identify hidden surfaces. The camera
matrix adapter is tested with the pinned Plotly runtime. Clicks perform no native
CAD operations or AI calls, and cached face meshes are excluded from AI payloads.

The IEC connector exposed an independent clearance measurement failure. Nearly
redundant mesh edges made an offset convex profile fail the strict prism contract;
the planner previously hid that error and reported no measured rear profile.
Invalid offsets now fall back to intersecting 32 supporting half-planes, each
containing the measured points plus clearance. This keeps a conservative enclosing
profile without weakening convexity validation. Unrecoverable measurement errors
are passed to the AI as errors, rather than an absent feature.

Compiler version 7 extends measured rear relief and through passages to common
plates. Native checks verify contact preservation, rear coverage and unobstructed
full-depth passages. Historical compiler versions retain their earlier behavior;
rails still do not support rear relief. No connector dimensions or mounting pattern
were hardcoded. The saved IEC data produced one valid SMLib plate with two measured
part holes and five base holes, with no failed native checks.

Verification: the wider suite ran 119 cases (117 passed, two transient Windows file
access/cleanup errors). The final 26 focused cases, including both affected tests,
passed in 58.59 seconds. Five JavaScript tests cover pointer behavior and surface
depth/occlusion, and Ruff F checks pass. The final eight face-picker cases also
passed after positioning the direction arrow on surface material instead of the
potentially hidden plane origin. Private IEC data and exports are excluded from
the source package.

Live verification: clicked both flange sides in the browser, confirmed the rear
face and its two holes, and submitted the measured-cutout request through the app.
The subscription model selected rear-profile-0 and preserved five M3 base holes.
After reloading the saved project to clear stale development-time schema objects,
the normal Generate button produced revision 70667bbf8c52, which the AI accepted
without correction. Prepare STEP download succeeded. Independent OCCT reopening
found one valid solid; a full-depth profile intersection measured 0.0 mm³ of
obstruction. Native checks reported no failures. The matching buttons, selected
face and completed mount were also verified visually. App restart/resume is advised
when developing against changed Pydantic schemas in an already-open session.
