"""One guided entry point, followed by one answer/revision composer."""

from hashlib import sha256

import streamlit as st

from .design_brief import started, save_brief
from .planning import missing_questions
from .ui_theme import conversation_panel, conversation_questions
from .workflow import plan_design


SETUP_FIELDS = (
    (
        "moving_components",
        "Moving or spinning parts",
        "What moves or rotates? Include travel and clearance, or unknown.",
    ),
    (
        "cable_routing",
        "Cable routing",
        "Where do cables/connectors exit? Include routing or bend space, or unknown.",
    ),
    (
        "service_access",
        "Tool and service access",
        "What must stay reachable for assembly, adjustment or removal?",
    ),
    (
        "motion_loads",
        "Loads and forces",
        "Weight/forces, directions and duty cycle; unknown is okay.",
    ),
)


def _brief_form(project, initial, ai_enabled):
    r = project.requirements
    values = {
        field: (
            getattr(r, field) or (r.access if field == "service_access" else None) or ""
        )
        for field, _, _ in SETUP_FIELDS
    }
    digest = sha256(str((r.purpose, r.quantity, values, r.locks)).encode()).hexdigest()[
        :12
    ]
    key = f"{'start' if initial else 'edit'}-brief-{project.id}-{digest}"
    with st.form(key):
        goal = st.text_area(
            "Fixture goal",
            value=r.purpose or "",
            max_chars=6000,
            height=90,
            placeholder="What should this fixture do? For example, hold a motor for inspection.",
            disabled="purpose" in r.locks,
        )
        answers = {
            "quantity": st.number_input(
                "How many parts should the fixture hold?",
                min_value=1,
                max_value=24,
                value=r.quantity,
                placeholder="Not specified",
                step=1,
                disabled="quantity" in r.locks,
            )
        }
        st.markdown("**Motion, routing & access**")
        st.caption(
            "Describe what you know. Type unknown if it is undecided; a blank answer stays unspecified."
        )
        for field, label, example in SETUP_FIELDS:
            answers[field] = st.text_area(
                label,
                value=values[field],
                max_chars=2000,
                height=68,
                placeholder=example,
                disabled=field in r.locks,
            )
        st.caption(
            "Choose mounting features and the manufacturing method in the model workspace."
        )
        if any(
            field in r.locks
            for field in ("purpose", "quantity", *(f[0] for f in SETUP_FIELDS))
        ):
            st.caption("Locked setup values can be unlocked in Advanced.")
        label = (
            ("Start design" if ai_enabled else "Save design brief")
            if initial
            else "Save setup"
        )
        submitted = st.form_submit_button(
            label, type="primary" if initial else "secondary"
        )
    return submitted, goal, answers


def render_conversation(project, planner, build, ai_enabled=True):
    """Return whether proposals may be shown; only explicit submits call planning."""
    if not started(project):
        st.markdown("**Start here: describe the job**")
        st.caption(
            "Tell us about the parts, motion and access needs before reviewing fixture concepts."
        )
        st.caption("Cable openings can be placed on the fixture after the first build.")
        if not ai_enabled:
            st.caption(
                "Offline mode saves your setup without calling an AI planner or generating CAD."
            )
        submitted, goal, answers = _brief_form(
            project, initial=True, ai_enabled=ai_enabled
        )
        if submitted:
            try:
                save_brief(project, goal, answers)
                if ai_enabled:
                    with st.spinner("Planning from your brief…"):
                        plan_design(project, planner, text="", start=True)
                st.rerun()
            except (ValueError, OSError) as error:
                st.error(str(error))
        return False

    questions = missing_questions(project.analysis, project.requirements)
    conversation_panel(project, questions)
    if project.error:
        st.error(
            project.error
            + (
                " The last valid fixture is retained."
                if project.current
                else " No CAD revision was saved for this attempt."
            )
        )
    with st.expander("Edit saved brief", expanded=False):
        st.caption(
            "Save changes to the setup and conversation context. This does not call the planner or rebuild the fixture."
        )
        submitted, goal, answers = _brief_form(
            project, initial=False, ai_enabled=ai_enabled
        )
        if submitted:
            try:
                save_brief(project, goal, answers)
                st.rerun()
            except (ValueError, OSError) as error:
                st.error(str(error))
    if not ai_enabled:
        st.caption(
            "Offline mode: setup and supported text commands remain available; no AI reply is requested."
        )
    active_questions = conversation_questions(project, questions)
    composer = (
        "Answer the design questions"
        if active_questions
        else "Request a revision"
        if project.current
        else "Discuss this proposal"
    )
    st.markdown(f"**{composer}**")
    text = st.chat_input(composer, key="design-reply-" + project.id)
    if text:
        with st.spinner("Updating the design conversation…"):
            generate = plan_design(project, planner, text=text, origin="user")
        if generate:
            build(project, change=text)
        st.rerun()
    return True
