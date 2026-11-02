"""UI-only selection persistence and refresh; never builds CAD or calls AI."""

import streamlit as st
from streamlit.errors import StreamlitAPIException

from .planning import missing_questions


def selection_signature(project):
    r = project.requirements
    return (
        project.id,
        r.interface_id,
        r.mounting_hole_ids,
        r.mounting_confirmed,
        r.part_attachment,
    )


def rerun_selection():
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        # AppTest and standalone callers run the whole script, not a fragment.
        st.rerun(scope="app")


def save_selection(project, requirements, highlights, description):
    """A failed lock/validation/save never replaces the accepted requirements."""
    if requirements == project.requirements:
        return False
    previous = (
        project.requirements,
        project.highlights,
        project.error,
        project.stage,
        list(project.messages),
    )
    try:
        project.requirements = requirements
        project.highlights = tuple(highlights)
        project.error = None
        project.stage = (
            "clarifying"
            if missing_questions(project.analysis, requirements)
            else "proposing"
        )
        project.messages.append(dict(role="user", content=description))
        project.save()
    except (ValueError, OSError):
        (
            project.requirements,
            project.highlights,
            project.error,
            project.stage,
            project.messages,
        ) = previous
        raise
    return True
