from pathlib import Path
import os
import streamlit as st
from fixture.intake import analyze_bytes
from fixture.viewer import assembly_figure
from fixture.project import Project
from fixture.planning import (
    patch_requirements,
    missing_questions,
    proposals,
    compile_plan,
    proposal_requirements,
)
from fixture.agent import plan_turn, offline_turn, review_turn
from fixture.controls import (
    requirement_controls,
    manufacturing_controls,
    passage_controls,
    screw_size_controls,
    retention_controls,
)
from fixture.hole_picker import hole_picker_controls
from fixture.face_picker import face_picker_controls
from fixture.access_controls import access_controls
from fixture.base_controls import base_controls
from fixture.subscription import subscription_turn, subscription_review, executable
from fixture.manufacturing import manufacturing_guidance
from fixture.workflow import plan_design, generate_with_feedback
from fixture.fasteners import resolve_clearances, clearance_summary, SOURCE
from fixture.step_export import prepare_step, prepared_step

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Fixture Studio", page_icon="◈", layout="wide")
st.markdown(
    "<style>.block-container{padding-top:1.4rem;padding-bottom:1rem} h1{font-size:2.2rem!important}"
    "[data-testid='stAppDeployButton']{display:none!important}</style>",
    unsafe_allow_html=True,
)
st.title("Fixture Studio")
st.caption("A measured part. A considered mounting approach. Real CAD.")


def short_text(text, limit=300):
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def load_part(data, name):
    with st.spinner("Reading STEP and identifying interfaces…"):
        analysis = analyze_bytes(data, name)
    st.session_state.project = Project.new(analysis)
    st.session_state.project.save()
    st.session_state.source_data = data
    st.session_state.source_name = name
    st.session_state.face_mode = False
    st.session_state.access_mode = False


def build(project, requirements=None, change="Generate reviewed proposal"):
    status = st.empty()
    try:
        generate_with_feedback(
            project,
            reviewer,
            mode,
            requirements,
            change,
            lambda s: status.info(s + "…"),
        )
        status.empty()
    except Exception as error:
        project.error = f"{type(error).__name__}: {error}"
    st.rerun()


with st.sidebar:
    st.header("Project")
    if st.button("New project"):
        st.session_state.clear()
        st.rerun()
    upload = st.file_uploader("STEP part", type=["step", "stp"])
    sample = st.selectbox(
        "Bundled specimen",
        [
            "synthetic_motor.step",
            "sensor_bracket.step",
            "mixed_hole_sizes.step",
            "hole_free_housing.step",
            "ambiguous.step",
            "multi_body.step",
            "transformed_motor.step",
            "unsupported_sphere.step",
        ],
    )
    load = st.button("Load example")
    st.caption("Examples are synthetic geometry, not manufacturer specifications.")
    if load or (upload and st.session_state.get("upload_id") != upload.file_id):
        try:
            load_part(
                (ROOT / "samples" / sample).read_bytes() if load else upload.getvalue(),
                sample if load else upload.name,
            )
            st.session_state.upload_id = upload.file_id if upload and not load else None
        except Exception as error:
            st.error(f"STEP intake failed: {error}")
    modes = ["ChatGPT subscription (Codex CLI)", "OpenAI API", "Offline commands"]
    mode = st.selectbox(
        "Conversation mode",
        modes,
        index=0 if executable() else (1 if os.getenv("OPENAI_API_KEY") else 2),
    )
    if mode == modes[0]:
        st.caption(
            "Uses your ChatGPT subscription allowance. No Platform API key. Measured summaries, conversation and generated review views are sent to OpenAI."
        )
    elif mode == "OpenAI API":
        st.caption("Model: " + os.getenv("OPENAI_MODEL", "gpt-6-astra"))
        st.caption(
            "Sends measured summaries, conversation and generated review views to OpenAI. Original STEP bytes stay local."
        )
    else:
        st.caption(
            "Limited deterministic commands; no model call or simulated AI response."
        )
    with st.expander("Resume a saved local project"):
        saved = sorted(
            (ROOT / "artifacts").glob("*/project.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if saved:
            chosen = st.selectbox(
                "Saved project",
                saved,
                format_func=lambda f: f.parent.name[:12],
                key="resume-project-path",
            )
            if st.button("Resume project"):
                try:
                    st.session_state.project = Project.load(chosen)
                    st.session_state.pop("source_data", None)
                    st.rerun()
                except Exception as error:
                    st.error(str(error))
if "project" not in st.session_state:
    st.info("Upload a STEP or load a bundled specimen to start.")
    st.stop()
p = st.session_state.project
a = p.analysis
r = p.requirements
planner = (
    subscription_turn
    if mode == modes[0]
    else plan_turn
    if mode == modes[1]
    else lambda a, r, messages, current: offline_turn(messages[-1]["content"])
)
reviewer = (
    subscription_review
    if mode == modes[0]
    else review_turn
    if mode == modes[1]
    else None
)
with st.sidebar:
    st.caption("Stage: " + p.stage)
    st.caption("STEP imported as one complete part.")
    if p.current:
        st.caption(
            "Export selected revision: generated fixture solids only, in millimeters. The uploaded part is excluded."
        )
        if st.button("Prepare STEP download"):
            try:
                with st.spinner("Converting and verifying solid STEP…"):
                    prepare_step(p.current)
            except Exception as error:
                st.error(f"STEP export failed: {error}. Native CAD is retained.")
        step_file = prepared_step(p.current)
        if step_file:
            st.download_button(
                "Download STEP (.step)",
                step_file.read_bytes(),
                file_name=f"fixture-{p.current.id}.step",
                mime="application/step",
            )
        st.caption(
            "The ZIP contains USD BRep CAD, requirements, the operation plan, checks and AI feedback. It also includes STEP after preparation."
        )
        st.download_button(
            "Export CAD + design record",
            p.export(False),
            file_name=f"fixture-{p.current.id}.zip",
            mime="application/zip",
            on_click=lambda: setattr(p, "stage", "exported"),
        )
        ids = [rev.id for rev in p.revisions]
        selected_revision = st.selectbox(
            "Revision history",
            ids,
            index=ids.index(p.active_id),
            format_func=lambda rid: next(
                v.changes[:45] + " · " + rid[:6] for v in p.revisions if v.id == rid
            ),
        )
        if st.button("Restore selected revision"):
            p.restore(selected_revision)
            st.rerun()
    st.caption(
        "All distances in millimeters. Geometry checks do not establish operating performance."
    )
left, right = st.columns([2.2, 1], gap="large")
with left:
    st.subheader(a.source_name)
    st.subheader("Design choices")
    if st.session_state.pop("close_hole_picker", False):
        st.session_state.pick_mode = False
    if st.session_state.pop("close_face_picker", False):
        st.session_state.face_mode = False
    face_button, hole_button = st.columns(2)
    if face_button.button("Select mounting face", width="stretch"):
        st.session_state.access_mode = False
        st.session_state.face_mode = True
        st.session_state.pick_mode = False
    if hole_button.button("Select mounting holes", width="stretch"):
        st.session_state.access_mode = False
        st.session_state.pick_mode = True
        st.session_state.face_mode = False
    face_mode = st.session_state.get("face_mode", False)
    pick_mode = st.session_state.get("pick_mode", False)
    if st.button('Select openings / keep-clear areas', width='stretch'):
        st.session_state.access_mode = True
        st.session_state.face_mode = st.session_state.pick_mode = False
        st.rerun()
    access_mode = st.session_state.get('access_mode',False)
    selecting = pick_mode or face_mode or access_mode
    with st.expander("View options", expanded=False):
        toggles = st.columns(5)
        source = toggles[0].checkbox("Source", True, disabled=selecting)
        fixture = toggles[1].checkbox("Fixture", True, disabled=selecting)
        evidence = toggles[2].checkbox("Mounting holes", True, disabled=selecting)
        dimensions = toggles[3].checkbox("Dimensions", False, disabled=selecting)
        envelopes = toggles[4].checkbox("Access volumes", False, disabled=selecting)
        compare = st.checkbox(
            "Overlay previous revision",
            False,
            disabled=selecting or not (p.current and p.current.parent),
        )
    previous = (
        next((v for v in p.revisions if p.current and v.id == p.current.parent), None)
        if compare
        else None
    )
    if access_mode:
        access_controls(p)
    elif face_mode:
        face_picker_controls(p)
    elif pick_mode:
        hole_picker_controls(p)
    else:
        st.plotly_chart(
            assembly_figure(
                a,
                r.interface_id,
                p.current,
                source,
                fixture,
                evidence,
                dimensions,
                envelopes,
                previous,
                highlight_ids=p.highlights
                or (
                    p.current.requirements.mounting_hole_ids
                    if p.current
                    else r.mounting_hole_ids
                ),
            ),
            width="stretch",
            config={"displaylogo": False},
        )
    if p.current and not pick_mode:
        c = st.columns(3)
        c[0].metric("Source instances", len(p.current.plan.placements))
        c[1].metric(
            "Fixture volume",
            f"{p.current.metrics['volume_mm3']:,.0f} mm³",
            f"{p.current.metrics['volume_mm3'] - previous.metrics['volume_mm3']:+,.0f} mm³"
            if previous
            else None,
        )
        c[2].metric("Revision", p.current.id[:6])
        if p.current.requirements != r:
            st.info(
                "The viewer shows the last valid revision. Generate to apply edited requirements."
            )
    retention_controls(p)
    screw_size_controls(p)
    if r.part_attachment == "screws" or r.surroundings == "bolt":
        st.caption(
            f"Clearance holes default to [ISO 273 medium]({SOURCE}). No clearance entry is required."
        )
    if r.interface_id:
        try:
            clearances = resolve_clearances(a, r)
            st.caption(clearance_summary(clearances))
            if any(c.basis.startswith("Assumed") for c in clearances):
                st.caption(
                    "Unspecified screw sizes are assumed from the measured openings. Threads are not identified; size and fit can be overridden in Advanced."
                )
        except ValueError as error:
            st.warning(str(error))
    passage_controls(p)
    manufacturing_controls(p)
    base_controls(p)
    with st.expander("Advanced — mounting evidence", expanded=False):
        options = [None] + [i.id for i in a.interfaces]
        selected = st.selectbox(
            "Attachment interface",
            options,
            index=options.index(r.interface_id),
            format_func=lambda x: x or "Select a candidate",
        )
        if selected != r.interface_id:
            try:
                p.requirements = patch_requirements(
                    r,
                    dict(
                        interface_id=selected,
                        mounting_hole_ids=(),
                        mounting_confirmed=False,
                        part_attachment="unselected",
                        envelopes=(),
                    ),
                )
                st.rerun()
            except ValueError as error:
                st.error(str(error))
        if selected:
            i = next(i for i in a.interfaces if i.id == selected)
            st.write(i.confidence)
            st.dataframe(
                [
                    dict(feature=h, diameter_mm=d, x_mm=c[0], y_mm=c[1])
                    for h, d, c in zip(i.hole_ids, i.diameters, i.centers)
                ],
                hide_index=True,
            )
            chosen_holes = st.multiselect(
                "Fastener holes (exclude ports or central openings)",
                list(i.hole_ids),
                default=list(r.mounting_hole_ids or i.hole_ids),
                format_func=lambda h: (
                    f"{h} · Ø {i.diameters[i.hole_ids.index(h)]:.3f} mm measured"
                ),
            )
            if st.button("Use selected measured holes"):
                if not chosen_holes:
                    st.error("Select at least one measured hole.")
                else:
                    p.requirements = patch_requirements(
                        r,
                        dict(
                            mounting_hole_ids=tuple(chosen_holes),
                            mounting_confirmed=False,
                            part_attachment="screws",
                        ),
                    )
                    st.rerun()
            st.caption(
                "Outline colors identify measured bore sizes, not screw threads. Frame Z points into the part; fixture Z ≤ 0."
            )
        else:
            st.caption(
                "Select a mounting face above, with or without holes. This list is an optional alternative."
            )
        st.caption(" · ".join(a.limitations))
    requirement_controls(p)
    if p.current:
        feedback = next(
            (f for f in reversed(p.feedback) if f.build.revision_id == p.current.id),
            None,
        )
        if feedback:
            if feedback.review:
                st.caption("AI review: " + short_text(feedback.review.summary, 220))
            with st.expander("AI design feedback", expanded=False):
                st.caption(
                    f"{feedback.provider} · {feedback.outcome.replace('_', ' ')} · attempt {feedback.attempt} of 2"
                )
                if feedback.review:
                    st.write(feedback.review.summary)
                    for finding in feedback.review.findings:
                        st.write("• " + finding)
                    for question in feedback.review.questions:
                        st.write(question)
                if feedback.note:
                    st.info(feedback.note)
                st.caption(
                    "AI feedback supplements the geometric checks; it does not establish operating strength or performance."
                )
        with st.expander("Validation results", expanded=False):
            st.dataframe(
                [
                    {
                        key: c.model_dump()[key]
                        for key in (
                            "result",
                            "name",
                            "measured",
                            "units",
                            "method",
                            "tolerance",
                            "features",
                            "correction",
                        )
                    }
                    for c in p.current.checks
                ],
                hide_index=True,
                width="stretch",
            )
        with st.expander("Operation plan and provenance"):
            st.json(p.current.plan.model_dump())
with right:
    st.subheader("Design conversation")
    brief = st.text_area(
        "Design brief",
        placeholder="What should this fixture do? Describe the task and any preferences.",
        key="design-brief-" + p.id,
        height=100,
    )
    st.caption(
        "Start with a brief, or leave it blank to continue your saved conversation. I will ask relevant questions and prepare a proposal."
    )
    if st.button("Start design", type="primary", disabled=reviewer is None):
        with st.spinner("Planning with AI…"):
            plan_design(p, planner, text=brief, start=True)
        st.rerun()
    if reviewer is None:
        st.caption(
            "Choose an AI conversation mode to use Start design and automatic feedback. Offline generation runs geometric checks only."
        )
    if p.error:
        st.error(
            p.error
            + (
                " The previous valid design is unchanged."
                if p.current
                else " No CAD revision was saved for this attempt."
            )
        )
    with st.container(height=240 if p.messages else 100):
        if not p.messages:
            st.caption(
                "Describe your task. I will use the measured interfaces and ask about decisions that affect the fixture."
            )
        for m in p.messages:
            with st.chat_message(m["role"]):
                if m["role"] == "assistant" and len(m["content"]) > 400:
                    st.write(short_text(m["content"]))
                    with st.expander("Read full response"):
                        st.write(m["content"])
                else:
                    st.write(m["content"])
    text = st.chat_input("Describe the task or request a revision")
    if text:
        with st.spinner("Planning from measured features…"):
            generate = plan_design(p, planner, text=text, origin="user")
        if generate:
            build(p, change=text)
        st.rerun()
    questions = missing_questions(a, r)
    if questions:
        st.info("\n\n".join(questions))
    if r.interface_id:
        st.subheader("Mounting proposals")
        st.caption(
            f"Concept dimensions: thickness {r.thickness:g} mm · margin {r.margin:g} mm · part gap {r.gap:g} mm."
        )
        st.caption(" ".join(r.assumptions))
        accepted = st.checkbox(
            "Accept displayed concept assumptions",
            value=r.assumptions_accepted,
            key="proposal-assumptions-" + p.id + str(r.assumptions_accepted),
        )
        if accepted != r.assumptions_accepted:
            p.requirements = patch_requirements(r, {"assumptions_accepted": accepted})
            p.save()
            st.rerun()
        if reviewer:
            st.caption("Generate builds CAD, runs checks and requests AI feedback.")
        options = proposals(a, r)
        if not options:
            try:
                compile_plan(a, r, require_ready=False)
            except ValueError as error:
                st.warning(str(error))
        for prop in options:
            with st.container(border=True):
                st.markdown("**" + prop.title + "**")
                st.write(prop.rationale)
                if prop.composition in ("l_bracket", "bridge"):
                    dims = prop.dimensions
                    st.caption(
                        f"Height {dims['mount_height_mm']:.1f} · depth {dims['base_depth_mm']:.1f} · width {dims['width_mm']:.1f} mm"
                    )
                with st.expander("Design details"):
                    st.caption(
                        f"{int(prop.dimensions.get('base_hole_count', 0))} base attachment holes, separate from the selected part holes."
                    )
                    if prop.dimensions.get("rear_region_count"):
                        st.caption(
                            f"{int(prop.dimensions['rear_region_count'])} rear clearances; {int(prop.dimensions.get('rear_passage_count', 0))} through passages. Unselected recesses may remain blind."
                        )
                    if prop.composition == "l_bracket":
                        st.caption(
                            "Side ribs: "
                            + (
                                "yes"
                                if (
                                    r.reinforce
                                    if prop.reinforce is None
                                    else prop.reinforce
                                )
                                else "no"
                            )
                        )
                    st.caption("Concept dimensions; load capacity is not verified.")
                    if guidance := manufacturing_guidance(
                        r.fabrication, prop.composition
                    ):
                        st.caption(guidance)
                    st.caption(prop.surroundings)
                    if prop.unresolved:
                        st.caption(
                            "Assumptions / unresolved: " + "; ".join(prop.unresolved)
                        )
                if st.button(
                    "Generate " + prop.title,
                    key="generate-" + prop.id,
                    disabled=bool(questions),
                ):
                    try:
                        build(
                            p,
                            proposal_requirements(r, prop),
                            "Generate " + prop.title,
                        )
                    except ValueError as error:
                        st.error(str(error))
