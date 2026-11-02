# Development changelog

These dated checkpoints preserve the implementation history through November 1,
2026. Branch names, test counts and outstanding items describe each checkpoint;
use [README.md](README.md) for the current submission and setup instructions.

## Final submission — November 2, 2026

The final application revision and the user-recorded
[video demonstration](FixtureStudio-demo.mp4) are consolidated on `main`.
The README now leads with the demonstration, setup, workflow and supported scope.
The recording previously listed as outstanding is complete. Detailed engineering
decisions and validation evidence remain in [Notes.md](Notes.md).

## Changing fixture type and placing openings again — November 1, 2026

Switching between a plate, rails, L-bracket and bridge retains each opening's ID
and diameter but marks it **Needs placement**. Generate the new fixture first,
then choose **Place next opening** or **Place on this fixture**, click the new
surface, and select **Place opening and rebuild**. Repositioning replaces that
opening; it does not add a duplicate. Pending openings are visibly listed and
absent from CAD/STEP until placed. Earlier revisions keep their original holes.
Other edits within the same fixture type retain valid saved positions.

A bridge has a horizontal mounting platform; an L-bracket has an upright wall.
Switching to a bridge does not preserve a requirement for a horizontally mounted
shaft normal to the mounting face. The proposal explains this difference before
generation; no automatic rotation or reinterpretation of the brief occurs.

The local app now disables automatic source-code reload. Restart Streamlit after
code updates so an active CAD session uses one consistent set of data contracts.
Feedback and planner boundaries validate serialized record data rather than relying
on Python class identity, preventing the reported same-name `BuildFeedback` error.

## Questions together and reliable opening saves — November 1, 2026

The conversation shows all currently unanswered design questions in one visible
checklist. Answer them together in the reply box. Saved answers are reused; only a
new dependency or ambiguous answer should require another round. Once ready,
choose **Generate** on a proposal without answering a separate permission question.
The controller no longer hides setup questions after the first three.

CAD saving now has an isolated recovery path for the Windows temporary-file rename
failure seen when adding an opening. After three local retries, the app passes the
same native SMLib solids to one hidden export process (30-second timeout), verifies
the reopened CAD, and publishes it atomically. It does not alter dimensions or ask
AI to repair a storage failure. If recovery fails, the last valid fixture remains.

## Place openings after the first design — November 1, 2026

Generate the fixture first, then choose **Add a fixture opening** above its preview.
Click a flat wall, base or rib side on the generated fixture and enter the
**Opening diameter (mm)**. The circle previews the location and size without changing
CAD. **Add opening and rebuild** creates a checked revision with a real round
through-hole. It does not require a matching hole or recess in the uploaded STEP.

Under **Existing fixture openings**, resize or remove an opening and rebuild.
Positions stay in the fixture coordinate frame through revisions of the same type; each opening
belongs to a fixture body and is not automatically repeated for each workpiece.
STEP includes these holes. Restoring a prior revision restores its opening choices.

Cable routing is no longer a setup question. Add cable openings after the first
fixture build using the opening tool; previously supplied routing requirements
are preserved and required openings not yet placed remain marked pending.
For an older project that requires selection before generation, tell the
conversation to defer cable-opening placement until after the first build.
**Select source access features** still handles measured source openings/keep-clear
regions; the older measured-recess control is available under **Advanced**.

Current scope is circular holes on flat fixture faces aligned with X, Y or Z,
0.5–500 mm diameter, within the bounded CAD operation budget. Holes need a complete
0.5 mm geometric rim and a clear path through the fixture assembly. Crossed edges,
existing holes, obstructing panels and invalid topology reject the revision and
retain the last valid CAD. These checks do not establish strength, cable bend radius
or connector fit. Curved/sloped entry surfaces and rectangular/slot openings are not
supported by this placement tool.

## Guided conversation, part colors and formed bends — November 1, 2026

New projects start in one visible **Fixture goal** form. Enter the task and number
of parts, then answer **Moving or spinning parts**, **Tool and
service access**, and **Loads and forces**. Blank means unspecified; type `unknown`
when undecided or explicitly say none. **Start design** saves these answers and
asks the AI to resolve the remaining details before proposing a fixture. Offline
mode uses **Save design brief** without an AI call. Quantity is not assumed.

After setup there is one message box: **Answer the design questions**, **Discuss
this proposal**, or **Request a revision**, depending on the current step. Revision
requests go there. **Edit saved brief** is collapsed and saves setup changes without
calling the AI or rebuilding. Saved questions survive project resume. Unanswered
planner questions prevent generation; geometric checks still guard every build.

Separate fixture parts have consistent individual preview colors, with legend
entries identifying each body. Uploaded workpieces and an imported base remain gray.
Colors persist across revisions and source visibility changes; geometry is unchanged.

For a formed L-bracket, choose **Fabrication → Sheet metal — tabs & welding →
Tabs & welded joints → Sheet construction → Bent L-bracket with welded ribs**.
The wall and base become one continuous 90° sheet bend; optional ribs remain separate
parts and are trimmed around its inside curve. There is no welded wall/base seam
or tab between those two flanges. Rib-to-base locating tabs remain optional.
**Inside bend radius (mm; 0 = automatic)** defaults to the sheet thickness; the
outside radius equals inside radius plus thickness. Generate a revision to apply it.

The actual radius must match the material and tooling, as described in
[SendCutSend's bending process guidance](https://sendcutsend.com/faq/how-do-you-bend-parts/).
This option models the formed geometry, not springback, press-brake access, weld
strength or a developed flat pattern. It currently supports 90° L-brackets; other
families use separate cut panels. Existing saved designs keep their construction
choice. STEP includes analytic curved surfaces and separate welded support bodies.

Reproduce the bent demo and a thickness/joint revision:

```powershell
.\.venv\Scripts\python.exe scripts/demo_sheet_metal.py --bent
```

## Sheet metal: tabs and welding — November 1, 2026

In **Fabrication → Manufacturing method**, choose **Sheet metal — tabs & welding**
and save. **Fixture thickness (mm)** becomes the common sheet thickness. Open
**Tabs & welded joints** to choose locating tabs/slots or weld-only butt joints,
adjust tab width/count, slot clearance per side and weld root gap. Generate a
revision to apply changes. Saving controls does not rebuild CAD or call the AI.

The **Separate cut panels** route creates flat panels for screw-mounted plates, rails,
L-brackets and bridges. A ribbed L-bracket has four panels: wall, base and two ribs.
Tabs fit into matching through slots at the base; the rib-to-wall seams are butt
joints. Bridges use tabs at the leg/platform and leg/foot joints. Tab width is
derived unless specified, and an unspecified L-bracket base grows to accommodate
the requested tabs. Selected part holes and base-hole counts remain unchanged.

The default slot allowance is **0.15 mm per side (0.30 mm total)**, with a zero
root gap and two tabs per tabbed joint. This is an editable concept allowance,
informed by [fabrication guidance](https://sendcutsend.com/blog/mastering-tab-and-slot-design-for-efficient-metal-fabrication/),
not a universal fit standard. Check actual sheet/cutting tolerances and coatings.
Native checks cover panel thickness, inter-panel interference, retained tabs,
clear slots, 1 mm slot edge lands and sampled weld lands. Rear clearances become
through cuts because flat sheets cannot contain blind pockets.

**Prepare STEP download** exports the generated panels as separate solids at their
assembled positions, without the uploaded part. **Export CAD + design record**
also includes `sheet-metal.json`: panel thicknesses, joint pairs, seam endpoints,
tabs, slots, root gaps and welding notes. It contains STEP after preparation.
No weld beads, weld sizing/strength, bent-sheet unfolding, DXF nesting or kerf
compensation are generated. This first route accepts 0.5–12 mm sheet and plain
through fastener holes; recessed seats, driver pockets and hole-free sheet
retention need further construction rules. Solid rib fillets/corner finishing
are inactive for sheet, with their saved settings retained for other methods.

Reproduce the synthetic example, including a thickness/tab-count revision and
verified STEP exports:

```powershell
.\.venv\Scripts\python.exe scripts/demo_sheet_metal.py
```

The script prints the saved project, STEP and design ZIP paths under `artifacts`.
Resume that project from the sidebar to inspect both revisions. No AI credential
or live model call is needed for this deterministic demo; normal conversation
supports the new sheet settings through the existing bounded planner.

## Selection reliability — November 1, 2026

Mounting face, hole and opening selection now share one persistent 3D viewer. Switching
between them preserves the camera and model instead of loading a second scene.
Hole clicks highlight immediately and save as an ordered, complete selection;
delayed updates cannot drop newer picks. Repeated clicks keep holes selected.
Use **×** in the selected-hole list or **Clear hole selection** to remove them.
Selecting a different mounting face still clears incompatible holes.

Large STEP models now transfer their selection geometry once per viewer mount.
Later picks send only selection IDs, and the selected face shares one outline and
direction arrow instead of hundreds of duplicate rendered overlays. Project saves
reuse compact immutable geometry records. The original STEP measurement and export
precision are unchanged; no preview decimation is involved.

The active selection button is highlighted. Opening selection sends only its small
set of measured aperture overlays; it keeps the mounting face, selected screw holes
and camera. Changing categories does not reload the source geometry or the page.

## Clearer editing and continuous bracket corners — November 1, 2026

**Display settings** groups **Objects**, **Overlays**, and **Edit & compare**.
Enable **Edit fixture dimensions**, choose a named setting, read its description,
enter a value, and choose **Apply dimension and rebuild**. The panel distinguishes
the value in the saved CAD from the current requirement. Automatic corner values
show their derived size. A fixed preview caption replaces floating dimension markers;
these values are design settings, not measurements of arbitrary displayed edges.
Dimension locks are available in a collapsed section.

**Design conversation** now shows the current step, next question and latest reply.
Earlier dialogue and selection/save activity are collapsed; the complete original
conversation remains available to the planner.

New L-bracket revisions apply manufacturing corner finishing continuously across
the joined base, wall and ribs. This removes the small square ledges above the
previously chamfered or rounded base corners. The native CAD validation checks for
leftover material in those corner regions, and the finish is included in STEP.
**Generate a new revision** to update an existing design; historical CAD and exports
remain reproducible.

## Automatic rib fillets — November 1, 2026

Newly generated ribbed L-brackets round the two inward rib-to-base joints in SMLib.
The default radius is the smaller of **1.5 mm**, **thickness / 4**, and the space
available at the joint. Under **Fabrication → Rib-to-base fillets**, turn this off
or set a radius up to 2 mm (further limited by the bracket geometry). Generate a new
revision to apply the settings; existing saved CAD stays unchanged.

The rounded surfaces are included in **STEP** and the reproducible design bundle.
Through passages and screw holes are cut after the fillets and checked as before.
This currently applies to these two L-bracket joints, not arbitrary edge rounding.
Fillets do not establish load capacity or fatigue life. Unsupported native fillet
combinations fail recoverably; reduce the radius or turn the option off.

## Simplified workspace — November 1, 2026

The model preview and fixture thickness stay visible. Open **Choose mounting face
and holes** to change the mounting selection; it starts open until a mounting face
is confirmed. **Display settings** contains overlays and fixture dimension editing.
Detailed settings are grouped in **Mounting**, **Fabrication**, and **Advanced**
tabs below the thickness control. All settings remain available and retain their
saved values when switching groups. Additional proposals are under **More fixture
concepts** after the first two choices.

The sidebar groups part import, assistant settings, saved projects, revision history
and technical exports. STEP preparation remains directly accessible. Existing
projects can continue through the conversation without reopening a starting brief.

## Thickness and preview update — October 31, 2026

**Fixture thickness (mm)** is now visible below the viewer under **Fixture
dimensions**. Editing it saves the requirement immediately. For an existing
fixture, choose **Rebuild with this thickness** to regenerate CAD through the
normal checks and AI-review workflow. Until then, the previous revision stays
visible and its thickness is identified. This changes the fixture, not the
uploaded STEP. Locked thickness values remain protected.

Generation and revision restore now return to the assembly preview with the
fixture visible, even when started from a face, hole or opening picker. Use
**View generated fixture** to inspect the CAD alone, or **View assembly** to see
it with the uploaded part. Selection categories continue to show the source for
picking. Failed rebuilds retain the last valid CAD and show the error.

## Feature expansion — October 30, 2026

Features **1–6** are implemented on `feature/fixture-tools-1-6`. The rollback
baseline is commit `3a66d5c`; the feature work has not been merged into `main`.

| Feature | What is available |
| --- | --- |
| 1. Selected access | Click measured faces, holes or rear profiles for full-through openings and finite keep-clear areas. Cuts follow thickness revisions and are checked against final native geometry. |
| 2. Existing base | Upload a second STEP, select its contact face and holes, and position it using in-plane offsets/rotation. The fixture copies the measured base pattern. |
| 3. Retention | Convex-envelope contour nests, open cylindrical saddles, closed collars and split clamps with separate caps, alongside existing screw mounts and trays. |
| 4. Dimensions | Set **Fixture thickness (mm)** below the viewer, or enable **Edit fixture dimensions** to edit/lock other supported values. Rebuild through the normal revision and AI-review workflow. |
| 5. Hardware | Optional part/base counterbores, 90° countersinks, hex nut pockets and finite screwdriver access. Native checks cover voids, sidewalls and seat floors. |
| 6. Manufacturing geometry | Printing chamfers exposed base corners; machining rounds them and adds cutter relief to rectangular openings. Method selection needs no material, printer or slicer settings. |

UI Man supplied the coordinated presentation refresh and hardware controls, with
existing widget callbacks and backend contracts preserved. Manufacturing corner
size defaults to `min(2 mm, thickness / 3)` and is editable in the dimension panel. This is a
concept assumption. New projects enable the rules; old projects keep their original
geometry until the manufacturing method is saved or changed.

The final complete suite passed **165 tests**, followed by **4 passing dimension/
pointer tests** for the live click-selection fix (overlapping runs). The new connector,
split-clamp and contour-nest demos generated real SMLib solids, exported STEP and
reproduced from their ZIP records. A real subscription-model revision changed the
connector's part counterbores to countersinks, preserved its base and through-opening
selections, generated CAD and received an **accepted** AI concept review.

The earlier **3 hours 30 minutes** below is the user-reported baseline. No new
cumulative duration has been supplied.

**Implemented and verified on Windows x64 / Python 3.12.10.** Both native kernels,
the Streamlit workflow, revisions, native checks, USD BRep round trips and clean
lockfile installation have been exercised. A real three-turn conversation using
the local Codex CLI's **ChatGPT subscription sign-in** generated and revised a
six-part fixture without an API key. The separate OpenAI API backend is implemented
and tested with test doubles; no API-key-backed live call has been made.

## Planner recovery follow-up — October 30, 2026

Planner follow-up: measured opening selections now round-trip through AI planning
without being mistaken for unknown features. Explicitly free-floating fixtures
use **None — free floating** under attachment to surroundings; their selected part
screws remain in place. Failed planning keeps saved choices/CAD and records the
reason in the conversation, so it can be addressed on the next Start design attempt.
The local project JSON also retains the latest validated decision and error for
debugging. It is not included in the public source or fixture export.

Face and hole picks now save immediately and remain highlighted when switching
selection categories. Picking a face does not preselect its holes. Mode changes
update the workspace without rerunning the conversation or proposals. Examples
are collapsed under **Try an example**. Verification: **184 tests passed** in the
full run, followed by **48 passing affected integration checks** after the final
UI fixes, plus real-browser selection checks.

## Baseline checkpoint — October 30, 2026

**Total project time so far: 3 hours 30 minutes (3.5 hours), reported by the user.**
This is the cumulative checkpoint total, not an additional development interval.

- Working flow: STEP upload and measurement, mouse selection of mounting faces/holes,
  conversational requirements, Start design, proposals, SMLib generation, AI feedback,
  revisions/restore and verified STEP export.
- Supported fixtures: plates, rails, ribbed L-brackets, bridges, and rectangular
  locating trays with optional external-strap slots for parts without mounting holes.
- Design controls include manufacturing method, screw-size suggestions, automatic
  standard clearances, configurable base-hole counts and real through passages.
- Verified examples include the supplied motor and IEC connector, unrelated synthetic
  parts, and hole-free tray geometry. Latest full suite: **126 passing tests**, plus
  **8 passing workflow tests** after the final prompt adjustment; Ruff F checks passed.
- Public source is available on [GitHub](https://github.com/lrosu02/fixture-studio).
  Credentials, private uploads and local projects are excluded.

Remaining: the continuous demo recording, a live API-key-backed test, and broader
geometry/engineering capabilities. Contact remains sampled; operating strength and
exact source-to-fixture BRep collision are not validated. The suggested next feature
was selecting openings and keep-clear areas directly in 3D; that is now implemented
in the feature expansion above.
See the [plan checkpoint](IMPLEMENTATION_PLAN.md#implementation-checkpoint--october-30-2026)
and [engineering record](Notes.md#checkpoint-and-total-time--october-30-2026).
