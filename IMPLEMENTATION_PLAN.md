# AI fixture design tool implementation plan

Build a conversational CAD tool that accepts an existing STEP part, learns what the user needs to do with it, proposes mounting approaches, and generates an editable fixture using NVIDIA SMLib. The user reviews the result, requests changes, and exports real CAD geometry.

This is a handoff specification for the implementation agent. The six brushless motors are a demonstration scenario, not a fixed product configuration. The application must derive its mounting interface, quantity, layout, and fixture construction from the uploaded geometry and conversation. No motor dimensions, mounting patterns, or six-position layouts belong in the general application logic.

## Sheet-metal extension checkpoint — November 1, 2026

**Post-build opening extension on `codex/click-through-openings`:** generated fixture
surfaces accept exact mouse positions for sized circular through-holes, independent
of source openings. Compiler 14 records bounded cuts, native edge/path checks,
resize/remove revisions and STEP export. New projects may defer cable-hole placement
until the first fixture exists, with unplaced access marked pending. Curved/sloped
entry surfaces and noncircular openings remain outside this placement tool's scope.
Verification: 273 full-suite Python tests and 20 JavaScript viewer tests passed,
including native STEP void checks, resize/remove/restore and invalid-cut retention.

**Follow-up on `codex/design-conversation-flow`:** guided initial operating-context
questions now precede proposals; follow-ups and revisions share one clearly labeled
composer. Separate fixture bodies use stable individual preview colors. Compiler 13
adds a continuous 90° wall/base bend and curve-fitted welded ribs for L-brackets,
with typed bend records, native thickness/bend/interference checks and analytic STEP
export. Original cut-panel construction remains available and historical compiler-12
exports retain their behavior. Formed geometry does not establish tooling feasibility,
produce an unfolded blank or calculate weld strength. Details and test evidence are
in the current README/Notes sections; the checkpoint below describes the preceding
flat-panel implementation.

Follow-up acceptance: **258 Python regression tests** and **15 JavaScript viewer
tests** passed. Native formed-sheet tests cover gauge/radius revisions, retained
mounting holes, through openings, STEP cylindrical surfaces, ZIP reproduction and
rejection of a deliberately filled square corner. A separate copy of the saved
two-motor project also passed with three bodies and all twelve mounting holes.

The user authorized a tabs-and-welding manufacturing option. Work is isolated on
`codex/sheet-metal-tabs-welding` from `ac9000e`. Compiler 12 builds separate flat
sheet panels with integral locating tabs and through slots, or weld-only butt
joints, for the four screw-mounted structure families. Part patterns remain measured;
sheet geometry contains no motor-specific dimensions or mounting decisions.

Delivered controls select the method, sheet thickness, joint style, per-side slot
clearance, tab width/count and root gap. The AI's typed edit contract exposes the
same choices. Native validation checks panel thickness, panel interference, tabs,
slots and remaining slot/weld lands in addition to the existing hole/access checks.
Separate assembled panel solids export to verified STEP, and the reproducible
design ZIP contains a panel/joint schedule. A deterministic synthetic demo exercises
generation, thickness/joint revision, STEP reopening and ZIP reproduction.

Boundaries: flat 0.5–12 mm sheets and plain through fastener holes; no bend unfolding,
kerf compensation, DXF nesting, weld beads/sizing, hole-free sheet retention or
structural weld validation. The adjustable 0.15 mm-per-side default is a fabrication
concept allowance, not a universal standard. Detailed decisions and verification
are recorded in README.md and Notes.md. Earlier checkpoints below remain historical.

Acceptance evidence: **234 full-suite tests passed**, plus one added native imported-base
integration test and **15 JavaScript viewer tests**. The live browser exercised method
selection, atomic joint saves, generation and verified four-panel STEP download.

## Implementation checkpoint — October 30, 2026

**Cumulative project time: 3 hours 30 minutes (3.5 hours), supplied by the user.**
This records the working baseline before the next feature expansion. The original
specification below remains the reference; this checkpoint records actual delivery
and the deliberate extensions beyond its initial planar/circular input family.

| Ordered stage | Status at this checkpoint |
| --- | --- |
| 1–2: Dependencies and measurement | Verified Windows/Python 3.12 environment. CadQuery/OpenCASCADE imports and measures STEP; NVIDIA SMLib constructs real fixture BReps. Planar faces with or without circular holes can be selected. |
| 3–5: UI, executor and placement | Working upload, rotatable viewer, face/hole picking, manufacturing-method choice and row/grid placement. Bounded operations build plates, rails, ribbed L-brackets, bridges and rectangular locating/strap trays. |
| 6–7: Agent, checks and revisions | Start design, relevant questions, executable proposals, real ChatGPT-subscription integration, native checks, one bounded AI correction, requirement locks, last-valid preservation and revision restore. |
| 8: Generality and regression | Motor and IEC connector workflows exercised; synthetic six-part, unrelated-part, transformed-source and hole-free cases verified. Latest full run: 126 tests passed; final prompt change: 8 workflow tests passed. Ruff F checks passed. |
| 9: Package and record | README, engineering notes, pinned setup, permitted samples, demo scripts/records, USD BRep/design bundles and verified STEP export delivered. Public repository published and fresh clone verified. Continuous 1–3 minute screen recording remains outstanding; cumulative hours now recorded. |

Follow-up fixes already delivered include mixed-size hole selectors and screw-size
suggestions, automatic standard clearance holes, configurable base-hole counts with
a centered fifth L-bracket hole, full-depth cable passages, corrected mesh rendering,
concise proposals, matching face/hole selection buttons and support-face selection
without part screw holes. All fixture construction remains in SMLib; the STEP writer
transfers its generated BRep through the bounded OpenCASCADE export bridge.

The reusable workflow is working within these bounds, not unrestricted fixture
synthesis. Exact source/fixture BRep collision, structural/thermal/vibration validation,
conformal nests and articulated clamps remain outside the delivered scope. Trays do
not establish hold-down strength. The API-key backend has test-double coverage but
no live-key verification; the live integration uses ChatGPT subscription sign-in.

**Next checkpoint candidates (discussed, not yet implemented or scheduled):**

1. Select openings and keep-clear areas directly on the 3D part.
2. Import an existing base as a second part and derive both attachment interfaces.
3. Add split clamps, saddles, collars and contoured nests with matching validation.
4. Add on-model dimension editing, fastener recesses/captive-nut pockets, stronger
   manufacturing rules and fixtures containing different part types.

Repository: [Fixture Studio](https://github.com/lrosu02/fixture-studio).
Detailed verification and time provenance: [Notes.md](Notes.md#checkpoint-and-total-time--october-30-2026).

## Features 1–6 delivery checkpoint — October 30, 2026

The user subsequently authorized these six additions and a rollback branch.
Work is on `feature/fixture-tools-1-6`, created from the `3a66d5c`
3h30m baseline. This feature work has not been merged into `main`. No newer cumulative time estimate is asserted. The candidate list
above is historical; the table below is the current delivered scope.

| Order | Delivered behavior | Acceptance evidence |
| --- | --- | --- |
| 1 | Mouse-selected measured openings and finite keep-clear areas | Through cuts survive thickness revisions; missing cuts and damaged contacts are rejected. Stale/pointer-drag events do not alter picks. |
| 2 | Second STEP base and measured attachment pattern | Rotated/offset base patterns align in real STEP; base reference is shown but excluded from fixture CAD; ZIP reproduction and restore tested. |
| 3 | Convex contour nests, cylindrical saddles/collars, split clamps | Native cavity and required material checks; separate caps; transformed/repeated cylinder test and analytic STEP export. |
| 4 | On-model parameter labels and lock-aware rebuilds | Click-event test, actual Streamlit thickness revision, source-measurement preservation and lock/invalid-edit rejection. |
| 5 | Counterbores, 90° countersinks, nut pockets and finite tool access | Manufacturer profiles or explicit dimensions; native void/sidewall/floor checks; conical STEP topology verified. Base stock accounts for head recesses. |
| 6 | Geometry rules for printing and machining | Chamfered or rounded exposed base corners and rectangular-opening cutter relief; all four structure families tested; method/geometry preserved in revision exports. |

Validation: final complete suite **165 passed in 220.87 s**, plus **4 dimension/
pointer cases passed in 16.68 s** after the live click-selection fix. Earlier native
targeted verification passed 34 cases; these are overlapping runs.
The combined connector, clamp and nest demos all exported STEP and reproduced from
their ZIPs. A live ChatGPT-subscription revision changed connector part seats to
countersinks, preserved selected base/access data and received an accepted concept
review. The API-key provider still has no live-key verification.

Compiler version 9 and analysis version 3 extend the bounded contracts. Old
compiler versions keep their implementations; new fields default to inactive for
old records. STEP adapter version 2 transfers analytic cones in addition to the
existing planes/cylinders, without rebuilding fixture geometry in OpenCASCADE.
The 256-operation, 64-body and 24-instance limits still apply.

Limits: nests use a conservative convex envelope, cylindrical retention requires
complete analytic outer cylinders, and nut pockets require an assembled cover for
axial capture. Manufacturing rules do not prove build orientation, cutter access
everywhere or physical performance. Exact source/base-to-fixture collision and
load/preload/thermal/vibration analysis remain outside scope. Mixed different
workpieces in one fixture was not part of the approved six additions. The continuous
demo recording remains outstanding; executable demos and live records are available.

## Selection and planner reliability follow-up — October 30, 2026

Measured access references now share a catalog between AI context and validation;
rejected decisions retain diagnostics and preserve existing requirements/CAD.
Explicit free-floating attachment is supported. Face/hole choices save directly,
without a second confirmation, and persist across selection categories. A face
does not implicitly select its holes. Workspace-only mode changes avoid rerunning
the surrounding app; dependent design controls update together and Generate checks
the latest saved requirements before any build. Synthetic examples are collapsed.

Verification: **184 tests passed in the full run**, followed by **48 passing
affected integration cases** after final UI fixes, with real-browser selection
and rerun-counter checks. The private planner case was checked locally; its live
AI replay was blocked and is not claimed. Details and remaining limits are in
Notes.md. The user-reported 3h30m checkpoint remains historical; no new cumulative
duration is asserted.

## Thickness and preview follow-up — October 31, 2026

A visible fixture-thickness control saves the user's value and rebuilds on request
through the existing revision pipeline. Generated and restored CAD now exits
source-only selection mode, with direct fixture-only and assembly view buttons.
The focused 17-case check covers actual native thickness changes and STEP re-import,
all three selection modes, locked/invalid edits, restore and failed-build recovery.
See README and Notes for usage and verification. No new cumulative time is asserted.

## UI simplification follow-up — November 1, 2026

Optional controls are grouped into Mounting, Fabrication and Advanced tabs, with
details and secondary proposals collapsed. Thickness and generated-preview access
remain visible. Eager tab rendering preserves saved controls within the workspace
fragment; CAD/planning/storage contracts are unchanged. The affected 26-case UI
set passed, followed by seven overlapping app checks after proposal grouping.
Synthetic browser checks verified selection, first manufacturing edit, pending
thickness and fixture-only visibility without unintended builds or AI calls.
No new cumulative development time is asserted.

## Persistent mounting selection follow-up — November 1, 2026

Face/hole selection now uses one persistent scene and a stable camera. Ordered,
cumulative browser state prevents delayed saves from dropping newer picks; explicit
removal and incompatible-face changes remain supported. Regression checks cover the
actual component update lifecycle without an intervening unmount, plus saved-state
ordering and mode transitions. Verification details are in Notes.md. No new
cumulative development duration is asserted.

## Selection and dimension clarity / corner correction — November 1, 2026

- [x] Highlight the active face, hole or opening selection tool immediately.
- [x] Reuse one persistent scene for all three selection categories; preserve camera
  and mounting picks, and reject delayed access events.
- [x] Group display settings by objects, overlays and editing/comparison; show the
  current conversation step and collapse older dialogue/technical activity.
- [x] Replace floating dimension markers with a clear panel and fixed caption;
  explain settings, built vs pending values, automatic defaults and locks.
- [x] Compiler 11: finish joined L-bracket exterior corners continuously through
  base, wall and ribs, with native residual-material validation and verified STEP.
- [x] Preserve historical compiler output and test the real saved NEMA17 case in
  an independent project, including eight part holes and four base holes.

The above UI work was coordinated with UI Man. Detailed evidence and limitations
are in Notes.md; existing designs require a new revision to receive CAD changes.

## Large-part selection and rib fillets follow-up — November 1, 2026

Mounting selection requests immutable viewer geometry once per browser mount;
subsequent events carry selection IDs. Source meshes are not decimated. Candidate
face meshes remain available for ray tests, while only the selected outline and
direction arrow are rendered. Compact cached geometry serialization preserves the
existing atomic project-save format and reduces repeated save work.

Compiler **10** adds a bounded native SMLib edge-fillet operation for the two
inward L-bracket rib/base joints. Default radius is min(1.5 mm, thickness/4), further
bounded by available joint space. Fabrication controls and conversational changes
can disable it or specify a bounded radius. Versions 1–9 retain their geometry.
STEP adapter **3** transfers SMLib's zero-angle cone representation as an exact
cylinder. Native material/void sampling, existing hole/passage checks, USD reopening,
STEP reopening and bundle reproduction cover the extension. Detailed evidence and
remaining native-kernel limitations are recorded in Notes.md; no new cumulative
development duration is asserted.

**Product scope**

The first version supports parts with recognizable planar attachment faces and circular mounting-hole patterns. It constructs fixtures from a small vocabulary of plates, rails, supports, holes, slots, openings, and repeated placements. This permits meaningfully different designs with predictable modeling behavior.

The tool should be able to change the composition of a design: for example, replace a broad mounting plate with two supporting rails to expose an opening, or add supports and access cutouts. A chat interface that only edits dimensions in a fixed motor rack does not meet this product intent.

General conformal nests, arbitrary surface reconstruction, general sheet-metal unfolding, structural optimization, and unrestricted CAD synthesis are later extensions. The initial limitation is the supported geometry vocabulary, not the identity of the uploaded part.

The minimum supported STEP case is one selected component in its imported pose, represented by one solid or a small group of solids already in a common placement, with analytic planar mounting surfaces and recognizable circular holes. Any intended motion is described separately through requirements and clearance envelopes. A full assembly browser, automatic repair of imported CAD, recognition of fully modeled helical threads, and recovery of analytic features from arbitrary NURBS surfaces are outside the minimum. When several bodies are present, an initial body list or treating a confirmed group as one part is sufficient.

Automatic selection is required for the straightforward demonstration case. Ambiguous planes, segmented or chamfered holes, and uncertain contact regions may fall back to candidate selection or correction by the user. These fallbacks must use the uploaded measurements and be visible in the design record.

**Required user experience**

1. Upload a STEP file and immediately see the imported part in a rotatable viewer.
2. Describe the fixture's purpose, desired appearance, quantity, mounting preferences, and access requirements in ordinary language.
3. Answer a few relevant questions when necessary. The tool accepts unknown answers and records assumptions explicitly.
4. See the mounting features the agent identified, with their locations highlighted on the actual part.
5. Review the recommended mounting approach and, when useful, an alternative the tool can actually generate.
6. Generate a fixture and see it assembled with the uploaded part or repeated instances.
7. Inspect the reasoning, important dimensions, and supported geometric checks.
8. Receive a direct invitation to revise the design, with useful suggestions based on the current result.
9. Request changes in chat or through parameter controls, compare revisions, and restore a previous valid result.
10. Export the fixture's BRep CAD geometry and the design specification needed to reproduce it.

Users who provide complete requirements should not have to repeat them in a questionnaire. Questions should resolve the next consequential decision. Limit each clarification round to two or three short questions.

**UI design**

Use a local Python application with Streamlit and a Plotly 3D viewer. Keep the viewer visually dominant. Use a conversation column alongside it, with requirements and analysis details in expandable panels. Avoid building a separate JavaScript frontend or API service for the initial version.

| Area | Required behavior |
| --- | --- |
| Upload and project controls | Accept STEP/STP, load a bundled example, show the selected part, start a fresh project, and export the current revision. |
| Conversation | Accept the brief, show focused clarification questions, present mounting proposals, summarize completed actions, and accept revisions. |
| Assembly viewer | Orbit, zoom, fit to view, and show the original part plus generated fixture. Use distinct colors for source geometry, fixture geometry, and highlighted evidence. |
| Viewer toggles | Show or hide source parts, fixture bodies, mounting features, dimensions, and access or clearance envelopes. |
| Requirements panel | Show purpose, quantity, fabrication intent, layout preferences, appearance preferences, locked dimensions, and unresolved facts. Permit edits. |
| Mounting proposals | Show a recommendation and a genuinely supported alternative with concise tradeoffs. Provide Generate, Choose alternative, and Change requirements actions. |
| Validation panel | Show individual checks, their measured results, and whether each passed, failed, was inconclusive, or was not evaluated. |
| Revision controls | List completed revisions, summarize changes, compare with the previous version, and restore a selected valid version. |

Use buttons such as Show mounting holes or Show blocked access to highlight relevant geometry. Direct face picking is optional; selecting a labeled candidate from a list must work first.

Show progress only for actual work: reading STEP, identifying interfaces, planning the fixture, building geometry, checking geometry. Keep the previous valid assembly visible while a revision runs. Show native errors as recoverable explanations with an actionable next step.

**The conversation and decision workflow**

The application follows these stages: uploaded, analyzed, clarifying, proposing, generating, checking, presented, revising, and exported. A failed operation returns to a recoverable stage without erasing the current design.

At intake, extract facts already present in the user's request. The tool should ask about these topics only when they influence the design:

| Topic | Example question the tool may ask |
| --- | --- |
| Purpose | What operation should this fixture support: testing, inspection, assembly, or another task? |
| Quantity and arrangement | How many parts must it hold, and is footprint or individual access more important? |
| Motion and attached loads | Will anything rotate or move? What is attached to it, and what space must remain clear? |
| Attachment meaning | Is this the intended stationary mounting face? Are these holes intended for fasteners? |
| Fasteners | What are the nominal screw size and allowable engagement, if known? |
| Access | Which surfaces, ports, wires, connectors, or tools need access? From what direction? |
| Fixture attachment | How will the fixture attach to the bench, frame, machine, or other surrounding equipment? |
| Fabrication | How do you intend to manufacture it, and are there material, thickness, or tool constraints? |
| Appearance | Should the design prioritize a compact footprint, symmetry, an open frame, or a cleaner outer profile? |

An unknown answer is a valid requirement state. Geometry can proceed as a concept when the user accepts explicit assumptions. Missing facts that determine which surface may be mounted or whether an interface physically fits require clarification before claiming that design is valid.

Fabrication method influences the proposal and supported parameter rules. It does not automatically imply a complete CNC, printing, or sheet-metal manufacturability check. Explain unsupported fabrication requests and offer a supported route before generating.

Mounting proposals should cover both attachment relationships: part to fixture and fixture to its surroundings. Each proposal identifies the source features it uses, proposed structure, intended access, unresolved assumptions, and expected tradeoffs. Prefer two meaningful candidates over a large speculative list. Do not present an unimplemented option as generatable.

After generation, respond with a short explanation of the result and ask: Would you like to change the layout, spacing, mounting approach, access, or appearance? Suggested changes must correspond to operations the tool supports.

**Architecture and responsibilities**

Use CadQuery/OpenCASCADE for STEP intake and measurement. Use SMLib through usd-brep to construct all generated fixture CAD. Pass plain measured data between those layers. This avoids requiring the original part to be converted into SMLib before a fixture can be designed.

CadQuery documents STEP import and shape inspection. NVIDIA's package provides SMLib modeling and BRep USD export. The assignment requires SMLib to create or modify real CAD geometry; generating the fixture in SMLib satisfies that role. Explain the reused importer clearly in Notes.md. [CadQuery import and export](https://cadquery.readthedocs.io/en/latest/importexport.html), [CadQuery shape API](https://cadquery.readthedocs.io/en/latest/classreference.html), [NVIDIA package documentation](https://github.com/NVIDIA-Omniverse/usd-brep/blob/main/tools/pyproject/README.md).

| Component | Owns | Must not substitute for |
| --- | --- | --- |
| STEP importer | Source file parsing, units, source transforms, bodies, original meshes, and measured feature candidates. | SMLib construction of the fixture. |
| Feature analyzer | Mounting coordinate systems, hole grouping, interface candidates, provenance, and ambiguity detection. | User knowledge about operating intent or stationary versus moving components. |
| Requirements manager | User statements, preferences, unknowns, assumptions, and locked constraints. | Geometric measurements. |
| AI planner | Clarification, candidate selection, fixture composition, proposed edits, and concise explanations. | Executable arbitrary code or unmeasured CAD coordinates. |
| SMLib executor | Fixture solids, booleans, transformations, tessellation, and BRep export. | A guarantee of thermal or structural performance. |
| Validator | Defined alignment, spacing, access-envelope, dimensional, topology, and export checks. | An undefined overall safe or manufacturable badge. |
| Project state | Immutable source analysis, requirements, accepted plans, revisions, generated artifacts, and reports. | Long chat transcripts as the only source of design state. |
| UI | Interaction, preview, evidence, controls, and downloads. | Geometry or planning business logic. |

Start with a single application and separable Python modules. A separate process for native import or geometry work is a fallback if library interaction, crashes, or timeouts justify it. Avoid microservices, a database, authentication, deployment infrastructure, and a multi-agent orchestration framework in the initial version.

Use Python 3.12 and pin a compatible dependency set after the initial feasibility check. OCP publishes Windows wheels, and usd-brep documents Windows Python 3.12 support; their combined installation must still be tested. Avoid separately importing another OpenUSD runtime into the application process. [OCP distribution](https://pypi.org/project/cadquery-ocp/), [NVIDIA known issues](https://github.com/NVIDIA-Omniverse/usd-brep/blob/main/KNOWN_ISSUES.md).

NVIDIA's OCCT-to-USD converter accepts OCCT BRep files and requires a source build. Full source-part conversion is an optional future path, not a prerequisite for this architecture. [Converter documentation](https://github.com/NVIDIA-Omniverse/usd-brep/blob/main/tools/occt_to_usd/README.md).

**Shared data contracts**

Define and validate these records before implementing the agent. Keep units explicit and normalize the internal modeling frame to millimeters.

| Record | Required contents |
| --- | --- |
| Part analysis | Source identifier and hash, original units and normalization, source-to-local transform, selected bodies, bounds, preview mesh, named features, interface candidates, and analysis limitations. |
| Feature | Stable application identifier within the immutable source analysis, source face references, geometry type, measured position, axis or normal, dimensions, and supporting evidence. |
| Mounting interface | Reference plane, local origin and axes, grouped hole centers and axes, modeled diameters, available contact regions, excluded regions, and confidence explanation. |
| Requirements | Purpose, quantity, surrounding attachment, fabrication intent, motion/load description, access constraints, layout and appearance preferences, locked values, unknowns, and accepted assumptions. |
| Proposal | Referenced interface IDs, structural approach, placement plan, rationale, unresolved decisions, supported checks, and editable choices. |
| Fixture plan | Named bodies and operations, dependency order, interface references, transforms, clearances, fastening features, and source of each important parameter. |
| Validation report | Check type, involved features, method, units, tolerance, measured value, result, and suggested correction when available. |
| Revision | Parent revision, input changes, requirements snapshot, fixture plan, generated output references, validation report, and user-facing change summary. |

For consequential values, distinguish measured from STEP, supplied by the user, suggested by AI, and assumed by default. Modeled hole diameter must remain distinct from nominal fastener size and thread specification. Geometry alone may not contain thread or allowable engagement information.

Refer to source features by measured IDs in AI proposals. Resolve coordinates in deterministic code. Keep source geometry immutable, and regenerate the fixture from its plan on edits; do not depend on raw generated face indices staying stable after booleans.

The fixture-plan contract must restrict the model to the following operation families. Each operation has a unique identifier, explicit dependencies, a named coordinate frame, validated parameters, and parameter provenance. Unknown operations and references are rejected before execution.

| Operation family | Required inputs and deterministic rules |
| --- | --- |
| Place source instances | Quantity, interface reference, row or grid arrangement, pitch or explicit supported placements, and orientation. The application calculates transforms and checks count consistency. |
| Create stock | Body identifier, rectangular or cylindrical stock type, positive dimensions, and an interface- or layout-relative anchor. Dimensions may be explicit requirements or calculated from station bounds plus margins. |
| Add support | Parent stock reference, supported rectangular or cylindrical shape, dimensions, and attachment anchor. Check its intended connection to the supporting body. |
| Cut mounting pattern | Target body, measured interface ID, instance IDs, confirmed clearance-hole diameter, and cutting extent. The application copies measured centers and axes; the model never supplies replacements for those measurements. |
| Cut relief or access | Target body, supported box, cylinder, or slot shape, purpose, source feature or user-defined region, dimensions, and approach direction. Preserve the relationship to the associated requirement. |
| Combine bodies | Existing body IDs and a supported union or difference operation. Reject cycles, references to missing bodies, and reuse of invalid native handles. |

Use a small set of named placement rules, such as centered on the interface or spanning the bounds of selected stations. Do not evaluate model-generated formulas. Distinguish source measurements, editable design parameters, and derived values; compute derived coordinates and dimensions in application code. Put configurable limits on body count, operation count, and requested dimensions, and choose defaults during the feasibility check.

Both a common plate and split supports should be expressible using these same operations. This is the required composition flexibility; a general CAD programming language is unnecessary.

**STEP analysis and mounting discovery**

Support a selected part or a small group of bodies representing one part. Preserve their relative transforms. If a file contains an assembly, let the user choose the relevant component or group rather than treating every body as a separate item to replicate.

The first analyzer should:

1. Read the file, establish units, compute bounds, and prepare its preview mesh.
2. Identify planar faces, cylindrical features, and circular boundaries relevant to mounting.
3. Group coaxial surfaces and edges belonging to the same hole, including chamfered or segmented holes, to avoid duplicate counts.
4. Distinguish plausible holes from external bosses using topology and surface orientation where available; mark uncertain cases.
5. Group holes by candidate plane and direction, retaining the measured pattern without assuming equal pitch, four holes, or a standard bolt circle.
6. Establish a local attachment frame and keep the transform needed to align the source part and generated geometry.
7. Return candidate interfaces with evidence, then let the planner interpret their suitability for the requested task.

For ambiguous geometry, show candidate faces and ask the user to select or confirm. Manual corrections are permitted and must be recorded. Unsupported input should produce a useful limitation message, not fabricated measurements.

Contact regions need their own evidence. Retain the selected planar face's trimmed boundary and its holes or openings, then identify candidate support patches near the intended fasteners. Begin with circular or rectangular patches whose footprints can be checked against that face; exclude modeled protrusions and user-designated openings. If the implemented method samples a footprint instead of proving full containment, report that limitation. When a suitable patch cannot be established, ask the user to confirm or adjust the region and keep it marked as user-supplied. Hole alignment alone must not be reported as verification of a suitable contact footprint.

**AI planning and execution loop**

Use one tool-calling model with schema-validated outputs. Vision is optional supporting context; raw screenshots are not a source of precise dimensions. The core model input is the measured feature summary, requirements, supported operation vocabulary, and current validation results.

The agent needs bounded actions to request clarification, inspect or highlight features, submit mounting proposals, submit a fixture plan, request a geometry build, inspect check results, and propose a revision. These actions operate on application records and measured identifiers.

The controller, rather than model-generated text, decides when to call the executor and whether a proposed operation is supported. The model never executes Python or arbitrary shell commands. Uploaded filenames, metadata, and descriptive text remain source data.

For each generation attempt:

1. Check that the proposal has enough information and that assumptions are visible.
2. Validate the operation plan and its dependencies before calling SMLib.
3. Build candidate geometry without overwriting the previous valid revision.
4. Run the defined geometric checks and collect measured feedback.
5. Permit at most one bounded automatic repair attempt for a supported correction.
6. Present the valid result, or explain the remaining conflict and offer specific edits.

If a locked requirement conflicts with a new instruction, explain which constraint would need to change. Do not silently move mounting holes or relax clearance to make a build succeed.

**SMLib geometry vocabulary**

The first executor should compose a small number of well-tested operations:

- Create rectangular plates, beams, support blocks, and cylindrical bosses.
- Cut clearance holes and central reliefs using cylinders.
- Make simple slots from a rectangular region and circular ends.
- Transform and repeat parts or mounting features in a local frame.
- Union connected stock and supports; subtract access openings and material-removal pockets.
- Keep intended assembly bodies separate and preserve their placements.
- Tessellate generated BReps for viewing and export fixture BReps to USD.

Represent mounting-hole patterns as references to the source interface, not repeated literals invented by the model. Use the same placement transforms for displayed source parts and generated attachment features.

Prefer planar cuts and simple stock for the first build. Fillets, offsets, and shelling can be enabled individually after representative cases pass. They are not required merely to demonstrate use of the kernel. NVIDIA documents failures in some shelling and tessellation cases. [Known issues](https://github.com/NVIDIA-Omniverse/usd-brep/blob/main/KNOWN_ISSUES.md).

**Validation and the meaning of a passing check**

| Check | What it establishes |
| --- | --- |
| Source interpretation | Units, selected bodies, transforms, and required mounting features are available or explicitly confirmed. |
| Interface alignment | Each generated hole axis and center matches the selected measured interface under the assembly transform. |
| Dimensional constraints | Requested spacing, footprint limits, thickness, hole edge distances, and locked values are satisfied within stated tolerances. |
| Defined clearance envelopes | Fixture geometry and repeated placements avoid specified conservative volumes for moving parts, cables, tools, and access. |
| Attachment and connectivity | Intended supports join their supporting bodies; unintended detached pieces or missing material around holes are flagged. |
| Kernel validity | Each intended solid passes supported topology checks and has positive volume and sensible bounds. |
| Export integrity | Exported fixture BReps can be reopened, with body count, bounds, and volume compared within tolerances. |

Define numerical tolerances centrally in model units and include them in reports. Use explicit volumes for finite tool access; a ray alone describes visibility, not clearance for a tool's thickness. Identify deliberate contact zones separately from forbidden intersections.

The motor or other source part remains in the OCCT domain. Without a conversion bridge, SMLib does not have its exact BRep for collision tests. The MVP checks measured interfaces and explicitly modeled analytic keepout volumes. Label these methods accurately. Simple non-overlapping envelopes can certify the modeled clearance condition; overlapping conservative envelopes may be inconclusive rather than proof that the original detailed shapes collide.

Continuous running is a requirement that influences the tool's questions, access, spacing, and ventilation intent. A geometric check does not establish thermal performance, vibration resistance, fatigue life, or acceptable operating speed. The tool should show those items as unresolved engineering requirements when relevant. Manufacturer instructions illustrate why cooling and screw engagement are operating inputs; the uploaded motor's own specifications must supply its actual values. [Example manufacturer instructions](https://assets.horizonhobby.com/on/demandware.static/-/Sites-horizon-master/default/dw4e2d9714/Manuals/EFLPower32OutrunnerInstructions.pdf).

**Implementation sequence**

Implement the steps in order. Each step should leave a working vertical slice and satisfy its acceptance condition before dependent work begins. Complete verification, documentation, and demo preparation as part of the project.

| Step | Implementation work | Acceptance condition |
| --- | --- | --- |
| 1 Prove the dependencies | Establish the pinned Python environment; load a representative STEP and its mesh; create a simple SMLib solid with a hole; export and reopen it. | Both kernels work in the selected runtime and real SMLib CAD survives export. |
| 2 Inspect mounting features | Build immutable source analysis, units and transforms, candidate planes, grouped hole patterns, and feature highlighting. | The representative part's interface is measured correctly and an ambiguous case can be confirmed manually. |
| 3 Establish the application UI | Add upload, viewer, conversation, editable requirements, stage display, and persistent session state. | A user can load a part, describe the task, inspect evidence, and retain state across UI updates. |
| 4 Build the reusable executor | Implement the bounded geometry vocabulary and numeric fixture-plan contract; support one attachment interface and two structural compositions. | A plate and an open support composition can be generated from measured inputs and exported as SMLib BReps. |
| 5 Support placement and quantity | Add transformed instances, configurable quantity, layout constraints, and surrounding attachment features. | The same interface aligns correctly in different quantities and placements; six is ordinary input data. |
| 6 Integrate the agent | Add requirement extraction, relevant clarifications, evidence-based mounting selection, proposal comparison, and fixture-plan submission. | A fresh conversation reaches a supported design without a hardcoded motor decision or dimensions. |
| 7 Add checks and revisions | Integrate constraint and envelope checks, a bounded repair path, change summaries, last-valid preservation, and undo. | One conversational change updates geometry; a conflicting request fails recoverably without moving locked features. |
| 8 Verify generality and polish | Exercise the demo, a second unrelated part, changed transforms, and failure cases; improve labels, highlighting, and comparison. | The tool passes the core acceptance tests and the intended demo runs end to end. |
| 9 Package and record | Clean setup test, README, Notes, bundled permitted examples, demo recording, and hours report. | Another person can reproduce the quick start and view a 1–3 minute demonstration. |

At the end of Step 1, choose any needed process isolation or compatible package pinning. Do not spend the assignment building NVIDIA's source converter when the agreed architecture does not need it. If STEP intake remains blocked, document the blocker and seek a deliberate scope decision; do not quietly replace uploaded geometry with a canned mesh.

At the end of Step 4, verify that fixture construction really occurs in SMLib. Do not implement the fixture in CadQuery and use SMLib solely for display or export.

By the end of Step 6, require a complete input-to-fixture flow. Prioritize STEP input, measured mounting selection, SMLib construction, one genuine revision, and a reproducible export before simultaneous alternative previews, decorative styling, fillets, broad fabrication rules, and elaborate history UI.

**Acceptance tests for the coding agent**

Prioritize tests of behavior and geometry, not screenshots of success messages or tests that merely repeat implementation steps.

- Import a real permitted sample STEP. Confirm the measured mounting pattern against known reference dimensions.
- Import an unrelated part with a different hole count or spacing. Its fixture must follow that interface with no motor-specific logic.
- Rotate and translate the source part. Confirm the local attachment pattern and assembled alignment remain equivalent.
- Exercise a STEP containing several bodies for one part; preserve their relative placement and allow explicit body selection.
- Change quantity and layout in conversation. Check the count and transforms of source instances and fixture mounting features.
- Add an access requirement. Confirm that the generated operation plan changes structure or adds a real opening, and that the corresponding check updates.
- Request a width or spacing that conflicts with locked geometry. Preserve the old revision and explain the conflict.
- Leave operating loads, material, or thread specification unknown. Confirm the agent asks when relevant and does not invent those facts.
- Provide ambiguous hole candidates or unsupported geometry. Confirm the tool asks for selection or explains its current limitation.
- Trigger malformed model output, a kernel failure, and an API timeout. The app must recover without losing the source or current valid fixture.
- Export and reopen the fixture. Verify real BRep bodies, valid topology, and consistent geometric measurements.

The mandatory regression core is the representative STEP and known dimensions, a second unrelated mounting pattern, transform invariance, quantity changes, one access-driven composition change, one rejected conflicting edit, and BRep export/reimport. Test multi-body selection and advanced hole grouping to the level actually implemented; document any manual fallback. Error handling must cover malformed model output, recoverable kernel exceptions, and API timeouts. Native process-crash recovery is an additional requirement only if process isolation is implemented.

Cache source analysis and preview meshes. Reuse measured geometry for revisions. Use explicitly labeled prerecorded AI responses only for a separate replay or test mode; the recorded live demo should make clear when a real model call is used.

**Six motor demonstration scenario**

The demo uses a brushless motor STEP and the brief: I want a fixture for six of these motors so they can run continuously. Help me choose how to mount them, keep the fixture accessible, and give it a clean appearance.

The attached screenshot suggests a cylindrical motor with several small circular features and larger openings. It does not establish dimensions, threads, stationary components, or operating conditions. Use the actual STEP for measurements. Use the screenshot only as contextual illustration.

Expected demo behavior:

1. The tool imports the actual motor and identifies candidate mounting interfaces.
2. The user describes six motors and continuous operation. The tool asks what is attached to the shafts, which components rotate, and other missing facts that affect its proposal. These are application questions; they are not predetermined answers in the product.
3. With sufficient evidence, the agent recommends the rear screw-hole interface. It highlights the measured holes and explains why that interface suits the confirmed task. It requests confirmation if stationary-face meaning or fastener details remain ambiguous.
4. The tool proposes supported fixture compositions or layouts with tradeoffs based on the user's priorities. It should not always select the same arrangement for every prompt.
5. The chosen fixture is generated in SMLib and shown with six aligned instances of the imported motor.
6. The tool presents the result, its checked constraints, and unresolved assumptions, then asks whether the user wants changes.
7. The user requests a consequential edit such as more rear tool access, a different arrangement, or less material around a designated opening. The tool updates geometry while preserving the measured mounting interface.
8. The user exports the resulting fixture BRep and design record.

The demo must not force a rear-hole conclusion if the actual source file or user answers contradict it. Select a representative motor whose rear mounting features can be verified, and explain any user confirmations honestly.

Suggested recording allocation: 20 seconds for upload and brief, 25 seconds for clarification and feature evidence, 25 seconds for the mounting recommendation, 35 seconds for generation and checks, 35 seconds for a revision, and 15 seconds for export. Total: approximately 2 minutes 35 seconds. Trim actual waiting time transparently if needed.

**Repository and handoff deliverables**

Keep modules separated by the responsibilities above: application UI, STEP intake, feature analysis, requirements and schemas, AI planning, SMLib execution, validation, revision state, and export. Use a simple local project folder for source files and generated artifacts. Do not commit API credentials or private uploaded files.

The exported project should include the fixture USD BRep file, its versioned plan and parameters, requirements and assumptions, validation results, and source-file identity. A mesh preview may be included separately. Do not describe a mesh-only source-part preview as an exact BRep conversion of the motor.

README.md must explain the product, supported input family, setup and runtime requirements, model/API configuration, launch instructions, a quick-start example, and exports. Notes.md must explain the two-kernel architecture, the AI's bounded role, feature and validation limits, reused libraries, remaining work, and actual hours spent. Include the demo link and permitted sample data.

**Maintaining README.md and Notes.md during implementation**

README.md and Notes.md already exist in the project root. They contain the agreed concept and decisions, with implementation-dependent details explicitly marked as pending. Read both before coding, preserve their useful content, and update them as each stage becomes operational. These are submission deliverables, not documents to leave as planning templates.

README.md is the user's entry point. Complete it with:

- A concise description of the application that actually ships and its supported inputs and workflow.
- Verified prerequisites, supported platforms, Python version, pinned dependency installation, and any required native components.
- The actual AI provider and model configuration, exact environment variable names, and credential setup without including secrets.
- Exact commands for obtaining the repository, creating the environment, installing dependencies, and launching from the repository root. Test them in a clean environment.
- A reproducible quick start using the actual permitted sample STEP filename, an example user prompt, relevant clarification answers, a generation, a revision, and an export. Describe what the user should observe.
- The actual export formats, filenames or download behavior, limitations relevant to users, and the final demo link.

Notes.md is the engineering decision record. Complete it with:

- Final architecture and decisions, their rationale, and any changes from this plan that explain meaningful tradeoffs.
- The actual boundary between OpenCASCADE import/measurement and SMLib fixture construction, including the scope of collision and clearance checks.
- The runtime model/provider, prompt and tool design, structured-output validation, retry behavior, and handling of unknown requirements.
- Implemented features, unsupported cases, remaining bugs, manual fallbacks, numerical assumptions, and physical performance checks that remain outside the prototype.
- Reused components with their actual versions, source links, applicable licenses, modifications, and roles. Identify borrowed examples or code and sample-asset provenance and permission.
- AI tools and models actually used to develop the project, what they assisted with, and how their outputs were verified. Keep this separate from the model used by the application; the earlier Astra High recommendation concerned the coding agent only.
- Verification actually performed, with environment, commands or reproducible manual steps, results, and untested cases.
- Prioritized next steps informed by the working prototype, the demo link, and an accurate total-hours report.

| Implementation milestone | Documentation update |
| --- | --- |
| Dependencies and STEP intake | Record the tested runtime and dependency versions, native requirements, sample provenance, and real input limitations. |
| UI and launch path | Add the actual launch command and controls; start validating the quick-start instructions. |
| Geometry and AI integration | Record implemented operations, model configuration, interface discovery, and the real division of responsibilities between kernels. |
| Validation and revisions | Document check methods and tolerances, error recovery, measured test results, and remaining limitations. |
| Export and packaging | Verify all setup and quick-start instructions, document real output files, add the demo and hours, and reconcile both documents with the delivered code. |

Before handoff, replace the planning-status language with an accurate implementation status. Remove a pending marker only after the corresponding detail has been verified; otherwise state the remaining gap plainly. Do not invent commands, environment variable names, versions, sample dimensions, benchmarks, test results, or successful integrations. Keep desired future behavior in Notes.md as future work rather than advertising it as an implemented README feature.

Documentation is complete when another person can follow README.md from a clean checkout through the example and export, and Notes.md accurately explains what was built, what was reused, what was checked, and what remains. Keep both documents consistent with code changes and with each other. Retain the filenames README.md and Notes.md in the repository root.

The final handoff should state which steps and acceptance tests were completed and list any incomplete requirements. Do not claim the fixture is physically validated for continuous operation based only on a successful CAD demonstration.

**Definition of done**

A new user can upload a supported STEP, describe a fixture task, answer relevant questions, inspect a grounded mounting recommendation, generate real SMLib fixture geometry, request a meaningful change, and export a reproducible result. The six-motor scenario demonstrates that workflow, while a second input proves that it is a reusable tool.

The original plan required explicit authorization before coding. Implementation was
subsequently authorized; the dated checkpoint above records the delivered baseline.
