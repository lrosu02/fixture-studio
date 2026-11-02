import pytest

from fixture.agent import Action, Changes, planner_context
from fixture.planning import missing_questions
from fixture.project import Project
from fixture.questions import clean_questions
from fixture.workflow import plan_design
from tests.test_geometry import ready


@pytest.mark.parametrize(
    "question",
    [
        "Would you like to generate CAD now?",
        "Would you like me to generate the fixture?",
        "Shall I generate the CAD now?",
        "Do you want me to proceed with CAD generation?",
        "Ready to generate?",
    ],
)
def test_generate_invitations_are_not_design_requirements(question):
    assert clean_questions([question]) == ()


def test_cleanup_preserves_conditions_dimensions_and_design_decisions():
    questions = (
        "Would you like to generate CAD with four M3 base holes?",
        "Should I build the fixture in two parts?",
        "Confirm the rotating disc clearance before generating?",
        "Which mounting method?",
    )
    assert clean_questions([*questions, " which mounting method? "]) == questions


def test_all_known_questions_reach_planner_and_one_visible_reply():
    a, _ = ready()
    p = Project.new(a)
    known = missing_questions(a, p.requirements)
    assert len(known) > 3
    assert planner_context(a, p.requirements)["next_questions"] == known
    action = Action(
        action="clarify",
        changes=Changes(),
        questions=tuple(known),
        highlight_ids=(),
        explanation="Complete the setup together.",
    )
    assert Action.model_validate_json(action.model_dump_json()) == action
    assert not plan_design(p, lambda *args: action, start=True)
    replies = [m["content"] for m in p.messages if m["role"] == "assistant"]
    assert len(replies) == 1
    for question in known:
        assert replies[0].count(question) == 1
    assert p.stage == "clarifying" and not p.revisions


@pytest.mark.parametrize("kind", ["clarify", "build", "revise"])
def test_ready_proposal_does_not_require_another_permission_or_auto_build(kind):
    a, r = ready()
    p = Project(a, r)
    action = Action(
        action=kind,
        changes=Changes(),
        questions=("Would you like to generate CAD now?",),
        highlight_ids=(),
        explanation="Your proposal is ready.",
    )
    assert not plan_design(p, lambda *args: action, "Accept the displayed defaults")
    assert p.stage == "proposing" and not p.revisions
    assert p.last_planner_attempt["action"]["questions"] == []
    assert "select Generate" in p.messages[-1]["content"]
    assert not missing_questions(a, p.requirements)


def test_answered_checklist_can_proceed_without_repeating_setup():
    a, r = ready(motion_loads=None, moving_components=None, surroundings="unknown")
    p = Project(a, r)
    action = Action(
        action="propose",
        changes=Changes(
            motion_loads="unknown", moving_components="None", surroundings="clamp"
        ),
        questions=(),
        highlight_ids=(),
        explanation="Review the proposal and select Generate.",
    )
    assert not plan_design(
        p, lambda *args: action, "No motion; loads unknown; clamp it."
    )
    assert p.stage == "proposing" and not missing_questions(a, p.requirements)
    assert "Will anything" not in p.messages[-1]["content"]
    build = action.model_copy(update={"action": "build", "changes": Changes()})
    assert plan_design(p, lambda *args: build, "Generate it")


def test_real_followup_is_retained_alongside_generate_invitation():
    a, r = ready()
    p = Project(a, r)
    action = Action(
        action="build",
        changes=Changes(),
        questions=(
            "Would you like to generate CAD now?",
            "What is the rotating disc diameter?",
        ),
        highlight_ids=(),
        explanation="Confirm the swept space.",
    )
    assert not plan_design(p, lambda *args: action, "Generate it")
    assert p.stage == "clarifying"
    assert p.last_planner_attempt["action"]["questions"] == [
        "What is the rotating disc diameter?"
    ]


def test_specific_questions_replace_generic_duplicates_but_still_block_build():
    from fixture.ui_theme import conversation_questions

    a, r = ready(
        motion_loads=None,
        service_access=None,
        brief_answers_recorded=True,
        moving_components="Shaft rotates",
        fabrication=None,
    )
    p = Project(a, r)
    specific = (
        "What loads and directions apply, including motor torque and belt pull?",
        "Which tools need access, and what screwdriver clearance is needed?",
        "Which manufacturing method should I use, and is sheet thickness fixed?",
        "What is the pulley diameter?",
    )
    action = Action(
        action="build",
        changes=Changes(),
        questions=specific,
        highlight_ids=(),
        explanation="Resolve the remaining design details together.",
    )
    assert not plan_design(p, lambda *args: action, "Generate it")
    known = missing_questions(a, p.requirements)
    assert len(known) == 3
    assert conversation_questions(p, known) == specific
    assert p.stage == "clarifying" and not p.revisions
    assert p.messages[-1]["content"].count("manufacturing method") == 1
