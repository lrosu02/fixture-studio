from pathlib import Path
import os
import streamlit as st
from fixture.intake import analyze_bytes
from fixture.project import Project
from fixture.planning import (
    patch_requirements,
    missing_questions,
    proposals,
    compile_plan,
    proposal_requirements,
)
from fixture.agent import plan_turn, offline_turn, review_turn
from fixture.workspace import workspace, request_assembly
from fixture.subscription import subscription_turn, subscription_review, executable
from fixture.manufacturing import manufacturing_guidance
from fixture.workflow import plan_design, generate_with_feedback
from fixture.step_export import prepare_step, prepared_step
from fixture.ui_theme import (
    apply_theme,
    studio_header,
    workflow_strip,
    welcome_panel,
    project_overview,
    conversation_intro,
)

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Fixture Studio", page_icon="◈", layout="wide")
apply_theme()
studio_header()


def short_text(text, limit=300):
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def load_part(data, name):
    with st.spinner("Reading STEP and identifying interfaces…"):
        analysis = analyze_bytes(data, name)
    st.session_state.project = Project.new(analysis)
    st.session_state.project.save()
    st.session_state.source_data = data
    st.session_state.source_name = name
    st.session_state.pick_mode = False
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
    if project.current:
        request_assembly(project)
    st.rerun()


with st.sidebar:
    st.header("Project")
    if st.button("New project", width="stretch"):
        st.session_state.clear()
        st.rerun()
    st.caption("01 / IMPORT YOUR PART")
    upload = st.file_uploader("STEP part", type=["step", "stp"])
    with st.expander("Try an example", expanded=False):
        sample = st.selectbox(
            "Bundled specimen",
            [
                "synthetic_motor.step",
                "sensor_bracket.step",
                "mixed_hole_sizes.step",
                "hole_free_housing.step",
                "cylindrical_housing.step",
                "convex_housing.step",
                "flanged_connector.step",
                "ambiguous.step",
                "multi_body.step",
                "transformed_motor.step",
                "unsupported_sphere.step",
            ],
        )
        load = st.button("Load example", width="stretch")
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
    st.divider()
    st.caption("02 / DESIGN ASSISTANCE")
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
    workflow_strip()
    welcome_panel()
    st.stop()
p = st.session_state.project
a = p.analysis
r = p.requirements
workflow_strip(p, missing_questions(a, r))
project_overview(p, missing_questions(a, r))
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
    st.divider()
    st.caption("03 / REVISIONS & DOWNLOADS")
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
left, right = st.columns([1.6, 1], gap="medium")
with left, st.container(key="studio-workspace"):
    workspace(p, build)
    r = p.requirements
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
with right, st.container(border=True, key="studio-conversation"):
    st.subheader("Design conversation")
    conversation_intro()
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
                ):
                    if questions:
                        st.warning("Before generating: " + " ".join(questions))
                    else:
                        try:
                            build(
                                p,
                                proposal_requirements(r, prop),
                                "Generate " + prop.title,
                            )
                        except ValueError as error:
                            st.error(str(error))
