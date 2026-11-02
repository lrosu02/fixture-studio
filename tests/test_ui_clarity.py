from copy import deepcopy
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from fixture.dimensions import value, value_label, dimension_figure
from fixture.project import Project
from fixture.ui_theme import (
    conversation_sections,
    conversation_questions,
    reply_summary,
)
from tests.test_geometry import ready


def test_conversation_projection_keeps_original_transcript_and_latest_reply():
    messages = [
        dict(role="user", content="Hold this part for inspection."),
        dict(role="assistant", content="How will the fixture be attached?"),
        dict(
            role="user",
            content="3D mounting selection: face interface-4; explicit screw holes: h0",
        ),
        dict(role="user", content="Clamp it to the bench."),
        dict(role="assistant", content="Review the plate concept below."),
        dict(role="assistant", content="What would you like to change next?"),
        dict(role="user", content="Set fixture thickness to 8 mm."),
    ]
    original = deepcopy(messages)
    result = conversation_sections(SimpleNamespace(messages=messages))
    assert result["latest_user"]["content"] == "Clamp it to the bench."
    assert result["latest_reply"]["content"] == "Review the plate concept below."
    assert len(result["history"]) == 2 and len(result["activity"]) == 3
    assert messages == original


def test_current_question_and_history_are_separate():
    p = SimpleNamespace(
        current=None,
        error=None,
        messages=[
            dict(role="user", content="First brief"),
            dict(role="assistant", content="First reply"),
            dict(role="user", content="Latest request"),
            dict(role="assistant", content="Latest reply"),
            dict(role="user", content="Manufacturing method: 3D printing."),
        ],
    )
    ui = AppTest.from_string("""
import streamlit as st
from fixture.ui_theme import conversation_panel
conversation_panel(st.session_state.project, ['How will it attach?', 'Which material?'])
""")
    ui.session_state.project = p
    original = deepcopy(p.messages)
    ui.run()
    assert not ui.exception
    assert {x.label for x in ui.expander} >= {
        "Your latest message",
        "Earlier conversation",
        "Selection and save activity",
    }
    assert "Other setup details" not in {x.label for x in ui.expander}
    card = ui.get("html")[0].proto.body
    assert 'aria-label="Unanswered design questions"' in card
    assert card.count("<li ") == 2
    assert card.index("How will it attach?") < card.index("Which material?")
    assert "Answer the questions below together in one reply." in card
    assert all(not x.proto.expanded for x in ui.expander)
    assert any(x.value == "**Latest assistant reply**" for x in ui.markdown)
    assert p.messages == original


def test_current_planner_question_precedes_general_checklist_without_stale_replay():
    p = SimpleNamespace(
        error=None,
        stage="clarifying",
        last_planner_attempt={"action": {"questions": ["How much cable clearance?"]}},
    )
    assert conversation_questions(p, ["Choose a method"]) == (
        "How much cable clearance?",
        "Choose a method",
    )
    p.stage = "proposing"
    assert conversation_questions(p, []) == ()


def test_current_review_questions_use_same_answer_flow_without_stale_replay():
    review = SimpleNamespace(
        outcome="needs_input",
        build=SimpleNamespace(revision_id="current"),
        review=SimpleNamespace(questions=("Confirm the cable bend radius.",)),
    )
    p = SimpleNamespace(
        stage="clarifying", current=SimpleNamespace(id="current"), feedback=[review]
    )
    assert conversation_questions(p) == ("Confirm the cable bend radius.",)
    p.last_planner_attempt = {"action": {"questions": ["Which connector?"]}}
    assert conversation_questions(p) == ("Which connector?",)
    p.last_planner_attempt = {
        "action": {"questions": ["Would you like to generate CAD now?"]}
    }
    assert conversation_questions(p) == ("Confirm the cable bend radius.",)
    p.last_planner_attempt = None
    p.current = SimpleNamespace(id="different")
    assert conversation_questions(p) == ()
    p.current = SimpleNamespace(id="current")
    p.stage = "presented"
    assert conversation_questions(p) == ()


def test_all_merged_questions_are_visible_once_with_escaped_design_text():
    p = SimpleNamespace(
        current=None,
        error=None,
        stage="clarifying",
        last_planner_attempt={
            "action": {
                "questions": [
                    "Would you like to generate CAD now?",
                    "Which material?",
                    "which material?",
                    "What is the <max> load?",
                ]
            }
        },
        messages=[dict(role="assistant", content="Use the measured mounting face.")],
    )
    questions = (
        "Which material?",
        "How many parts?",
        "What must remain reachable?",
        "Should I generate a 4 mm or 6 mm wall?",
    )
    original = deepcopy(p.__dict__)
    ui = AppTest.from_string("""
import streamlit as st
from fixture.ui_theme import conversation_panel
conversation_panel(st.session_state.project, st.session_state.questions)
""")
    ui.session_state.project, ui.session_state.questions = p, questions
    ui.run()
    assert not ui.exception
    card = ui.get("html")[0].proto.body
    assert card.count("<li ") == 5
    assert card.count("Which material?") == 1
    assert "Would you like to generate CAD now?" not in card
    assert "What is the &lt;max&gt; load?" in card
    assert "Should I generate a 4 mm or 6 mm wall?" in card
    assert not any(x.label == "Other setup details" for x in ui.expander)
    assert p.__dict__ == original


def test_reply_summary_omits_repeated_questions_without_changing_transcript():
    questions = ("Which material?", "What load?")
    text = (
        "The measured mounting face is suitable.\n\n"
        "1. **Which material?**\n2. What load?\n\n"
        "Would you like to generate CAD now?"
    )
    p = SimpleNamespace(
        current=None,
        error=None,
        messages=[dict(role="assistant", content=text)],
    )
    original = deepcopy(p.messages)
    ui = AppTest.from_string("""
import streamlit as st
from fixture.ui_theme import conversation_panel
conversation_panel(st.session_state.project, ('Which material?', 'What load?'))
""")
    ui.session_state.project = p
    ui.run()
    assert not ui.exception
    assert reply_summary(text, questions) == "The measured mounting face is suitable."
    assert reply_summary("Explain why 'Which material?' matters.", questions) == (
        "Explain why 'Which material?' matters."
    )
    assert (
        ui.chat_message[0].markdown[0].value
        == "The measured mounting face is suitable."
    )
    full_reply = next(x for x in ui.expander if x.label == "Read full assistant reply")
    assert not full_reply.proto.expanded and full_reply.markdown[0].value == text
    assert p.messages == original


def test_legacy_generate_permission_only_shows_proposal_step_and_keeps_history():
    text = "Would you like to generate CAD now?"
    p = SimpleNamespace(
        current=None,
        error=None,
        stage="clarifying",
        last_planner_attempt={"action": {"questions": [text]}},
        messages=[dict(role="assistant", content=text)],
    )
    ui = AppTest.from_string("""
import streamlit as st
from fixture.ui_theme import conversation_panel
conversation_panel(st.session_state.project)
""")
    ui.session_state.project = p
    ui.run()
    assert not ui.exception and conversation_questions(p) == ()
    card = ui.get("html")[0].proto.body
    assert "Choose a fixture concept" in card
    assert "Unanswered design questions" not in card
    assert not ui.chat_message
    full_reply = next(x for x in ui.expander if x.label == "Read full assistant reply")
    assert not full_reply.proto.expanded and full_reply.markdown[0].value == text
    assert p.messages == [dict(role="assistant", content=text)]


def test_display_values_survive_selection_mode_and_do_not_touch_requirements():
    p = SimpleNamespace(id="display-project", current=SimpleNamespace(parent="parent"))
    ui = AppTest.from_string("""
import streamlit as st
from fixture.display_controls import render_display_controls
st.session_state.display = render_display_controls(st.session_state.project, st.session_state.selecting)
""")
    ui.session_state.project, ui.session_state.selecting = p, False
    ui.run()
    next(x for x in ui.checkbox if x.label == "Uploaded part").uncheck().run()
    next(x for x in ui.checkbox if x.label == "Keep-clear areas").check().run()
    before = dict(ui.session_state.display)
    ui.session_state.selecting = True
    ui.run()
    assert not ui.exception and all(x.disabled for x in ui.checkbox)
    assert dict(ui.session_state.display) == before
    ui.session_state.selecting = False
    ui.run()
    assert ui.session_state.display["source"] is False
    assert ui.session_state.display["envelopes"] is True
    assert ui.session_state["workspace-view-display-project-source"] is False
    assert not hasattr(p, "requirements")


def test_display_unavailable_controls_explain_why():
    ui = AppTest.from_string("""
import streamlit as st
from types import SimpleNamespace
from fixture.display_controls import render_display_controls
render_display_controls(SimpleNamespace(id='empty', current=None), False)
""").run()
    assert not ui.exception
    for label in (
        "Generated fixture",
        "Edit fixture dimensions",
        "Compare with previous revision",
    ):
        assert next(x for x in ui.checkbox if x.label == label).disabled
    assert any("Generate a fixture to enable" in x.value for x in ui.caption)


def test_derived_dimensions_use_real_policy_and_unknown_is_automatic():
    _, r = ready(manufacturing_features=True, process_radius=None, thickness=9)
    plan = SimpleNamespace(parameters={})
    assert value(r, plan, "process_radius") == 2
    assert value_label(r, plan, "process_radius") == "Automatic · 2 mm"
    assert value(r, plan, "mount_height") is None
    assert value_label(r, plan, "mount_height") == "Automatic"


@pytest.fixture
def dimension_project():
    a, r = ready(manufacturing_features=True)
    p = Project(a, r)
    p.generate()
    return p


def dimension_ui(monkeypatch, p):
    monkeypatch.setattr(
        "fixture.dimensions.component",
        lambda: lambda **kw: SimpleNamespace(picked=None),
    )
    ui = AppTest.from_string("""
import streamlit as st
from fixture.dimensions import dimension_controls
def build(p, r, description):
    st.session_state.builds.append((r, description))
dimension_controls(st.session_state.project, build)
""")
    ui.session_state.project, ui.session_state.builds = p, []
    return ui.run()


def test_dimension_panel_rebuild_keeps_measurements_and_explains_values(
    monkeypatch, dimension_project
):
    p = dimension_project
    original = p.requirements
    ui = dimension_ui(monkeypatch, p)
    assert not ui.exception
    assert any("Built value: 6 mm" in x.value for x in ui.caption)
    assert any("not a measured edge" in x.value for x in ui.caption)
    assert not next(
        x for x in ui.expander if x.label == "Dimension lock"
    ).proto.expanded
    next(x for x in ui.number_input if x.label == "New value (mm)").set_value(8).run()
    next(x for x in ui.button if x.label == "Apply dimension and rebuild").click().run()
    candidate, _ = ui.session_state.builds[0]
    assert candidate.thickness == 8 and p.requirements == original
    assert candidate.interface_id == original.interface_id
    assert candidate.mounting_hole_ids == original.mounting_hole_ids
    fig = dimension_figure(p.analysis, p.current, "process_radius")
    labels = [t for t in fig.data if t.meta and t.meta.get("dimension")]
    assert not labels
    caption = fig.layout.annotations[-1]
    assert caption.xref == "paper" and caption.yref == "paper"
    assert "Automatic · 2 mm" in caption.text


def test_dimension_lock_save_failure_rolls_back(monkeypatch, dimension_project):
    p = dimension_project
    ui = dimension_ui(monkeypatch, p)
    before, messages = p.requirements, list(p.messages)

    def fail_save(self):
        raise OSError("Injected lock-save failure")

    monkeypatch.setattr(Project, "save", fail_save)
    next(x for x in ui.checkbox if x.label == "Lock this dimension").check().run()
    next(x for x in ui.button if x.label == "Save dimension lock").click().run()
    assert not ui.exception and p.requirements == before and p.messages == messages
    assert any("Injected lock-save failure" in x.value for x in ui.error)


def test_legacy_model_pick_does_not_override_dropdown(monkeypatch, dimension_project):
    p = dimension_project
    click = {}

    def component(**kwargs):
        return SimpleNamespace(
            picked={"context": kwargs["data"]["context"], "field": click["field"]}
            if click
            else None
        )

    ui = dimension_ui(monkeypatch, p)
    monkeypatch.setattr("fixture.dimensions.component", lambda: component)
    click["field"] = "thickness"
    ui.run()
    selector = next(x for x in ui.selectbox if x.label == "Dimension to edit")
    assert selector.value == "thickness"
    selector.select("margin").run()
    assert not ui.exception
    assert (
        next(x for x in ui.selectbox if x.label == "Dimension to edit").value
        == "margin"
    )
