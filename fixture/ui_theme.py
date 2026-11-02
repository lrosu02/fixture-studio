"""Presentation helpers. These render existing state without changing a project."""

from html import escape
from pathlib import Path
import re

import streamlit as st

from .questions import clean_questions, merge_questions


def apply_theme():
    st.html(Path(__file__).with_name("studio.css"))


def studio_header():
    st.html(
        '<header class="studio-header">'
        '<div class="studio-brand"><span class="studio-mark" aria-hidden="true">◈</span>'
        "<div><h1>Fixture Studio</h1><p>Measured geometry. Thoughtful fixtures.</p></div></div>"
        '<span class="studio-tag">Design workspace</span></header>'
    )


def workflow_strip(project=None, questions=()):
    current = project.current if project else None
    pending = bool(current and current.requirements != project.requirements)
    if project is None:
        active = 0
    elif questions:
        active = 1
    elif current is None or pending:
        active = 2
    else:
        active = 3
    steps = (
        ("Import", "Bring in your STEP part"),
        ("Define", "Brief, motion & mounting"),
        ("Generate", "Build and check a revision"),
        ("Export", "Prepare your CAD download"),
    )
    items = []
    for index, (title, detail) in enumerate(steps):
        state = (
            "complete" if index < active else "active" if index == active else "waiting"
        )
        marker = "✓" if state == "complete" else str(index + 1).zfill(2)
        aria = ' aria-current="step"' if state == "active" else ""
        items.append(
            f'<li class="studio-step {state}"{aria}><span class="studio-step-number" '
            f'aria-hidden="true">{marker}</span><div><strong>{title}</strong>'
            f"<span>{detail}</span></div></li>"
        )
    st.html(
        '<ol class="studio-workflow" aria-label="Design workflow">'
        + "".join(items)
        + "</ol>"
    )


def welcome_panel():
    st.html(
        '<section class="studio-welcome"><span class="studio-eyebrow">YOUR NEXT FIXTURE STARTS HERE</span>'
        "<h2>From part to fixture.</h2><p>Bring in a STEP part and develop a mounting approach "
        "around its measured geometry. Inspect, refine, and export each design revision.</p>"
        '<div class="studio-welcome-cards">'
        "<article><span>01 / BRING YOUR PART</span><h3>Start with a STEP file</h3>"
        "<p>Use <b>STEP part</b> in the sidebar. Exploring first? Open <b>Try an example</b>, "
        "choose a specimen, and select <b>Load example</b>.</p></article>"
        "<article><span>02 / DEFINE THE SETUP</span><h3>Describe the job</h3>"
        "<p>Start with <b>Fixture goal</b> and motion, access and load notes in "
        "<b>Design conversation</b>. Choose mounting features in <b>Model preview</b>.</p></article>"
        "<article><span>03 / MAKE IT YOURS</span><h3>Review and refine</h3>"
        "<p>Generate a proposal, inspect the model and checks, and request changes. "
        "Prepare a STEP download when you are ready.</p></article>"
        '</div><p class="studio-welcome-note">STEP and STP files · dimensions in millimeters '
        "· synthetic examples included</p></section>"
    )


def project_overview(project, questions=()):
    current = project.current
    pending = bool(current and current.requirements != project.requirements)
    if pending:
        badge, kind = "Changes awaiting generation", "attention"
        hint = "The model shows your saved revision. Generate a new revision to apply your changes."
    elif current:
        badge, kind = "Revision " + current.id[:6], "saved"
        hint = "Inspect your fixture, refine the design, or prepare a STEP download in the sidebar."
    elif questions:
        badge, kind = "Define your setup", "neutral"
        hint = (
            "Answer the design questions together in Design conversation. Use Model preview for mounting choices."
            if project.requirements.purpose
            else "Start with Fixture goal and motion, access and load notes in Design conversation. Use Model preview for mounting choices."
        )
    else:
        badge, kind = "Choose a proposal", "saved"
        hint = "Review Mounting proposals in Design conversation and generate your preferred approach."
    source = escape(project.analysis.source_name)
    st.html(
        '<section class="studio-project" aria-label="Current project">'
        f'<div><span class="studio-eyebrow">CURRENT PART</span><strong title="{source}">{source}</strong>'
        f'<p>{hint}</p></div><span class="studio-status {kind}">{escape(badge)}</span></section>'
    )


def workspace_intro():
    st.caption(
        "Drag to rotate · scroll to zoom. Mounting selections are saved as you pick."
    )


def conversation_intro():
    st.caption(
        "Start with the guided brief. Use the reply box for follow-up answers and revisions."
    )


def is_activity_message(message):
    """Classify UI/workflow notes for display without changing the AI transcript."""
    text = message["content"].strip()
    return (
        text.startswith(
            (
                "3D mounting selection:",
                "Part retention:",
                "Manufacturing method:",
                "Sheet-metal joints:",
                "Screw sizes for selected holes:",
                "Make these measured rear recesses through passages:",
                "Attach to uploaded base ",
                "Set fixture thickness to ",
                "Dimension lock:",
                "Start design using my brief, saved conversation,",
                "Built ",
                "Offline mode: geometric checks only;",
                "Selected opening ",
            )
        )
        or text == "What would you like to change next?"
        or (
            text.startswith("Change ")
            and text.endswith("Preserve locked dimensions and rebuild.")
        )
        or (
            text.startswith("Selected ")
            and text.endswith("Generate a revision to apply it.")
        )
    )


def conversation_sections(project):
    """Return a read-only presentation of the full, original message records."""
    dialogue, activity = [], []
    for index, message in enumerate(project.messages):
        (activity if is_activity_message(message) else dialogue).append(
            (index, message)
        )
    latest_user = next(
        (entry for entry in reversed(dialogue) if entry[1]["role"] == "user"), None
    )
    latest_reply = next(
        (entry for entry in reversed(dialogue) if entry[1]["role"] == "assistant"), None
    )
    shown = {entry[0] for entry in (latest_user, latest_reply) if entry}
    return dict(
        latest_user=latest_user[1] if latest_user else None,
        latest_reply=latest_reply[1] if latest_reply else None,
        history=[message for index, message in dialogue if index not in shown],
        activity=[message for _, message in activity],
    )


def conversation_questions(project, questions=()):
    """Prefer the planner's current clarification over the general setup checklist."""
    attempt = getattr(project, "last_planner_attempt", None) or {}
    action = attempt.get("action") or {}
    clarifying = getattr(project, "stage", None) == "clarifying" and not getattr(
        project, "error", None
    )
    current = clean_questions(action.get("questions", ()) or ()) if clarifying else ()
    if clarifying and not current:
        revision = getattr(project, "current", None)
        latest = next(
            (
                record
                for record in reversed(getattr(project, "feedback", ()) or ())
                if revision
                and getattr(getattr(record, "build", None), "revision_id", None)
                == getattr(revision, "id", None)
            ),
            None,
        )
        if getattr(latest, "outcome", None) == "needs_input":
            current = clean_questions(
                getattr(getattr(latest, "review", None), "questions", ()) or ()
            )
    return merge_questions(current, questions)


def reply_summary(text, questions):
    """Hide exact repeated questions in the summary; retain the original transcript."""

    def key(value):
        return " ".join(value.split()).casefold().rstrip(" ?.!")

    shown = {key(question) for question in questions}
    lines = []
    for line in text.splitlines():
        candidate = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s+", "", line).strip().strip("*_")
        # The same cleaner also suppresses a saved permission-only prompt.
        if candidate and (key(candidate) in shown or not clean_questions((candidate,))):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def conversation_panel(project, questions=()):
    questions = conversation_questions(project, questions)
    sections = conversation_sections(project)
    pending = bool(
        project.current and project.current.requirements != project.requirements
    )
    if project.error:
        step, prompt = (
            "Resolve the last attempt",
            "Review the error below, then retry or describe a change.",
        )
    elif questions:
        step, prompt = (
            "Design questions",
            "Answer the questions below together in one reply.",
        )
    elif pending:
        step, prompt = (
            "Review your changes",
            "Choose Generate on a fixture concept to apply your saved changes to the CAD.",
        )
    elif project.current:
        step, prompt = (
            "Review the fixture",
            "Inspect the model, request a change, or prepare a STEP download.",
        )
    else:
        step, prompt = (
            "Choose a fixture concept",
            "Review the proposals below and generate the approach you want.",
        )
    checklist = (
        '<ol aria-label="Unanswered design questions" '
        'style="padding-left:1.3rem;margin:.65rem 0 0;color:#e4faf5;font-size:.86rem;line-height:1.6">'
        + "".join(
            f'<li style="margin:.4rem 0">{escape(question)}</li>'
            for question in questions
        )
        + "</ol>"
        if questions
        else ""
    )
    st.html(
        '<section class="studio-conversation-step" aria-label="Current design step">'
        '<span class="studio-eyebrow">CURRENT STEP</span>'
        f"<h4>{escape(step)}</h4><p>{escape(prompt)}</p>{checklist}</section>"
    )
    if sections["latest_user"]:
        with st.expander("Your latest message", expanded=False):
            st.write(sections["latest_user"]["content"])
    if reply := sections["latest_reply"]:
        original = reply["content"]
        text = reply_summary(original, questions)
        if text:
            st.markdown("**Latest assistant reply**")
            with st.chat_message("assistant"):
                st.write(
                    text if len(text) <= 650 else text[:650].rsplit(" ", 1)[0] + "…"
                )
        if text != original or len(text) > 650:
            with st.expander("Read full assistant reply", expanded=False):
                st.write(original)
    if sections["history"]:
        with st.expander("Earlier conversation", expanded=False):
            for message in sections["history"]:
                with st.chat_message(message["role"]):
                    st.write(message["content"])
    if sections["activity"]:
        with st.expander("Selection and save activity", expanded=False):
            for message in sections["activity"]:
                st.caption(message["content"])
