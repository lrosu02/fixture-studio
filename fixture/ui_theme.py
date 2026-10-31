"""Presentation helpers. These render existing state without changing a project."""

from html import escape
from pathlib import Path

import streamlit as st


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
        ("Define", "Choose the mounting setup"),
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
        "<p>Choose the mounting face or holes, then explain what the fixture should do "
        "in <b>Design conversation</b>.</p></article>"
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
        hint = "Choose mounting features below, then describe the job in Design conversation."
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
        "Choose mounting features on the model. Drag to rotate · scroll to zoom."
    )


def conversation_intro():
    st.caption("Describe the job, compare approaches, and request a revision.")
