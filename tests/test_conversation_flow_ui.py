from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest

from fixture.project import Project
from tests.test_geometry import ready


HARNESS = """
import streamlit as st
from fixture.conversation_ui import render_conversation
from fixture.agent import Action, Changes
def planner(a, r, messages, current):
    st.session_state.calls.append(list(messages))
    return Action(action='clarify', changes=Changes(), questions=('Confirm the mounting setup.',), highlight_ids=(), explanation='Your motion and access notes are recorded.')
def build(*args, **kwargs):
    st.session_state.builds.append((args, kwargs))
st.session_state.proposals_allowed = render_conversation(st.session_state.project, planner, build, st.session_state.ai)
"""


def app(project=None, ai=True):
    if project is None:
        a, _ = ready()
        project = Project.new(a)
    ui = AppTest.from_string(HARNESS, default_timeout=40)
    ui.session_state.project = project
    ui.session_state.ai = ai
    ui.session_state.calls, ui.session_state.builds = [], []
    return ui.run(), project


def area(ui, label):
    return next(x for x in ui.text_area if x.label == label)


def button(ui, label):
    return next(x for x in ui.button if x.label == label)


def fill_brief(ui):
    area(ui, "Fixture goal").set_value("Hold two motors for inspection.")
    next(x for x in ui.number_input if x.label.startswith("How many parts")).set_value(
        2
    )
    for label, text in (
        ("Moving or spinning parts", "Motor shafts rotate; leave 20 mm clear."),
        ("Tool and service access", "Screwdriver access from the front."),
        ("Loads and forces", "unknown"),
    ):
        area(ui, label).set_value(text)


def test_initial_flow_has_one_guided_form_and_no_competing_composer():
    ui, p = app()
    assert not ui.exception and not ui.chat_input
    assert {x.label for x in ui.text_area} >= {
        "Fixture goal",
        "Moving or spinning parts",
        "Tool and service access",
        "Loads and forces",
    }
    assert "Cable routing" not in {x.label for x in ui.text_area}
    assert not button(ui, "Start design").disabled
    assert (
        next(x for x in ui.number_input if x.label.startswith("How many parts")).value
        is None
    )
    assert ui.session_state.proposals_allowed is False
    assert not p.messages and not p.revisions and not ui.session_state.calls


def test_ai_start_saves_answers_once_and_does_not_generate():
    ui, p = app()
    fill_brief(ui)
    button(ui, "Start design").click().run()
    assert not ui.exception and not p.error and len(ui.session_state.calls) == 1
    assert p.requirements.quantity == 2 and p.requirements.motion_loads == "unknown"
    assert p.requirements.cable_routing is None
    assert "Cable routing: Not specified" not in p.messages[0]["content"]
    assert sum(m["content"].startswith("Design brief:") for m in p.messages) == 1
    assert not p.revisions and not ui.session_state.builds
    assert (
        len(ui.chat_input) == 1
        and ui.chat_input[0].placeholder == "Answer the design questions"
    )
    assert not any(x.label == "Start design" for x in ui.button)
    assert not next(
        x for x in ui.expander if x.label == "Edit saved brief"
    ).proto.expanded
    ui.run()
    assert len(ui.session_state.calls) == 1


def test_offline_start_saves_goal_without_planning_or_internal_instruction():
    ui, p = app(ai=False)
    fill_brief(ui)
    button(ui, "Save design brief").click().run()
    assert (
        not ui.exception and p.requirements.purpose == "Hold two motors for inspection."
    )
    assert p.requirements.brief_answers_recorded and len(p.messages) == 1
    assert (
        not ui.session_state.calls and not ui.session_state.builds and not p.revisions
    )
    assert len(ui.chat_input) == 1
    assert not any(x.label == "Start design" for x in ui.button)


def test_blank_goal_remains_in_initial_form_without_model_call():
    ui, p = app()
    button(ui, "Start design").click().run()
    assert not ui.exception and any(
        "Describe what the fixture" in x.value for x in ui.error
    )
    assert not ui.chat_input and p.requirements.purpose is None
    assert not p.messages and not ui.session_state.calls


def test_unbuilt_ready_proposal_uses_discussion_composer():
    a, r = ready()
    ui, _ = app(Project(a, r))
    assert not ui.exception and len(ui.chat_input) == 1
    assert ui.chat_input[0].placeholder == "Discuss this proposal"


@pytest.fixture
def built_project():
    a, r = ready()
    p = Project(a, r)
    p.generate()
    return p


def test_edit_saved_setup_preserves_cad_and_legacy_access_without_planning(
    built_project,
):
    p = built_project
    revision = p.current.id
    ui, _ = app(p)
    assert area(ui, "Tool and service access").value == p.requirements.access
    assert (
        len(ui.chat_input) == 1 and ui.chat_input[0].placeholder == "Request a revision"
    )
    area(ui, "Fixture goal").set_value("Updated inspection setup")
    button(ui, "Save setup").click().run()
    assert not ui.exception and p.requirements.purpose == "Updated inspection setup"
    assert p.requirements.service_access == "rear tools"
    assert p.current.id == revision and len(p.revisions) == 1
    assert not ui.session_state.calls and not ui.session_state.builds
    assert sum(m["content"].startswith("Design brief:") for m in p.messages) == 1


def test_revision_reply_does_not_add_a_new_start_instruction(built_project):
    p = built_project
    ui, _ = app(p)
    ui.chat_input[0].set_value("Leave more room for the connector.").run()
    assert not ui.exception and not p.error and len(ui.session_state.calls) == 1
    assert not any(
        m["content"].startswith("Start design using my brief") for m in p.messages
    )
    assert len(p.revisions) == 1 and not ui.session_state.builds


def test_failed_setup_save_preserves_previous_messages_and_cad(
    monkeypatch, built_project
):
    p = built_project
    ui, _ = app(p)
    original, messages, revision = p.requirements, deepcopy(p.messages), p.current.id

    def fail_save(self):
        raise OSError("Injected brief save failure")

    monkeypatch.setattr(Project, "save", fail_save)
    area(ui, "Fixture goal").set_value("Unsaved change")
    button(ui, "Save setup").click().run()
    assert not ui.exception and p.requirements == original and p.messages == messages
    assert p.current.id == revision and not ui.session_state.calls
    assert any("Injected brief save failure" in x.value for x in ui.error)
