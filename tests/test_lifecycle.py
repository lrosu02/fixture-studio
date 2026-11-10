"""Behavioral state transitions: publication, recovery, question ownership and AX."""

import json
from types import SimpleNamespace

import pytest

from fixture.agent import Action, Changes, planner_context
from fixture.contracts import DesignReview, RepairChanges
from fixture.lifecycle import (
    CadState,
    DesignPhase,
    active_questions,
    presentation,
    set_questions,
    workflow_state,
)
from fixture.planning import patch_requirements
from fixture.project import Project, ROOT
from fixture.workflow import generate_with_feedback, plan_design
from tests.test_geometry import ready


@pytest.fixture
def project():
    a, r = ready()
    return Project(a, r)


def test_readiness_is_pure_and_shared_with_agent(project):
    p = project
    first = p.generate()
    p.requirements = patch_requirements(p.requirements, {"thickness": 8})
    before = (p.stage, p.requirements, p.active_id, list(p.messages))
    state = workflow_state(p)
    assert state.cad == CadState.OUTDATED and state.phase == DesignPhase.CHANGES
    assert state.can_generate and state.can_export_saved_revision
    assert state.revision_id == first.id
    context = planner_context(p.analysis, p.requirements, p.current)
    assert context["workflow_state"] == state.model_dump(mode="json")
    assert (p.stage, p.requirements, p.active_id, p.messages) == before


def test_json_inspection_matches_controller_and_does_not_write(project, monkeypatch):
    from scripts.inspect_state import describe_project

    p = project
    p.generate()
    p.requirements = patch_requirements(p.requirements, {"thickness": 8})
    p.save()
    path = ROOT / "artifacts" / p.id / "project.json"
    before = path.read_bytes()

    def forbidden(*args, **kwargs):
        pytest.fail("Read-only inspection must not save or build.")

    monkeypatch.setattr(Project, "save", forbidden)
    monkeypatch.setattr(Project, "generate", forbidden)
    result = describe_project(path)
    assert result["workflow"] == workflow_state(p).model_dump(mode="json")
    assert "thickness" in result["changed_requirement_fields"]
    assert result["step"] == "not_prepared_or_invalid"
    assert path.read_bytes() == before


def test_review_questions_replace_old_planner_questions_and_survive_export_resume(
    project,
):
    p = project
    p.last_planner_attempt = {"action": {"questions": ["Old planner question?"]}}
    review = DesignReview(
        verdict="needs_input",
        summary="Choose a load direction.",
        findings=(),
        changes=RepairChanges(),
        questions=("Which load direction?",),
    )
    generate_with_feedback(p, lambda *args: review, "test")
    assert active_questions(p) == review.questions
    before = (p.stage, p.clarification)
    p.export()
    assert (p.stage, p.clarification) == before
    p.save()
    restored = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert workflow_state(restored) == workflow_state(p)
    assert workflow_state(restored).question_source == "review"
    assert not workflow_state(restored).can_generate


def test_failed_build_review_questions_are_visible_without_a_revision(project):
    p = project
    impossible = patch_requirements(p.requirements, {"max_width": 1})
    review = DesignReview(
        verdict="needs_input",
        summary="The width limit prevents a build.",
        findings=(),
        changes=RepairChanges(),
        questions=("Can the maximum width be increased?",),
    )
    generate_with_feedback(p, lambda *args: review, "test", impossible)
    state = workflow_state(p)
    assert state.cad == CadState.ABSENT and state.phase == DesignPhase.RECOVERY
    assert state.questions == review.questions
    assert "answer_questions" in state.next_actions
    restored = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert restored.error == p.error and restored.last_attempt == p.last_attempt
    assert workflow_state(restored).questions == review.questions


def test_failed_snapshot_publication_does_not_activate_new_cad(project, monkeypatch):
    p = project
    first = p.generate()
    before = p.requirements
    original_save = p.save
    calls = 0

    def fail_commit_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("Injected project snapshot write failure")
        original_save()

    monkeypatch.setattr(p, "save", fail_commit_once)
    with pytest.raises(OSError, match="snapshot"):
        p.generate(patch_requirements(before, {"thickness": 8}))
    assert p.current == first and p.requirements == before and len(p.revisions) == 1
    assert p.last_attempt.revision_id is None
    assert p.last_attempt.failure_kind == "cad_export"
    restored = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert restored.current == first and restored.error == p.error
    assert workflow_state(restored).can_export_saved_revision
    revised = p.generate(patch_requirements(before, {"thickness": 8}))
    assert revised.parent == first.id and revised.id != first.id and p.error is None


def test_failed_restore_is_atomic_and_successful_restore_clears_attempt_questions(
    project, monkeypatch
):
    p = project
    first = p.generate()
    second = p.generate(patch_requirements(p.requirements, {"thickness": 8}))
    p.stage = "clarifying"
    set_questions(p, "review", ("Second revision question?",), second.id)
    previous = (p.active_id, p.requirements, p.stage, p.clarification)
    with monkeypatch.context() as patch:

        def fail():
            raise OSError("Injected restore save failure")

        patch.setattr(p, "save", fail)
        with pytest.raises(OSError):
            p.restore(first.id)
    assert (p.active_id, p.requirements, p.stage, p.clarification) == previous
    p.restore(first.id)
    assert not active_questions(p) and p.last_attempt is None
    assert p.current == first


def test_planner_receives_same_state_and_does_not_build_without_request(project):
    p = project
    p.stage = "clarifying"
    set_questions(p, "review", ("Which direction?",))
    expected = workflow_state(p).model_dump(mode="json")
    seen = []

    def planner(a, r, messages, current, workflow_state=None):
        seen.append(workflow_state)
        return Action(
            action="propose",
            changes=Changes(),
            questions=(),
            highlight_ids=(),
            explanation="Ready",
        )

    assert not plan_design(p, planner, "Axial", start=True)
    assert seen == [expected] and not p.revisions and not active_questions(p)


@pytest.mark.parametrize("backend", ["api", "subscription"])
def test_both_live_adapters_receive_controller_question_ownership(
    project, monkeypatch, backend
):
    from fixture import agent, subscription

    p = project
    p.stage = "clarifying"
    set_questions(p, "review", ("Which direction?",))
    expected = workflow_state(p).model_dump(mode="json")
    action = Action(
        action="propose",
        changes=Changes(),
        questions=(),
        highlight_ids=(),
        explanation="Ready",
    )
    received = []
    if backend == "api":

        def call(schema, name, instructions, context, *args):
            received.append(context)
            return action

        monkeypatch.setattr(agent, "_api_decision", call)
        planner = agent.plan_turn
    else:

        def call(schema, instructions, context, *args):
            received.append(context)
            return action

        monkeypatch.setattr(subscription, "_subscription_decision", call)
        planner = subscription.subscription_turn
    plan_design(p, planner, "Axial")
    assert received[0]["workflow_state"] == expected
    assert received[0]["next_questions"] == ["Which direction?"]


def test_planner_save_failure_rolls_back_candidate_and_cannot_trigger_build(
    project, monkeypatch
):
    p = project
    before = (p.requirements, p.stage, p.clarification)
    action = Action(
        action="revise",
        changes=Changes(thickness=8),
        questions=(),
        highlight_ids=(),
        explanation="Thicker",
    )

    def fail():
        raise OSError("Injected planning save failure")

    monkeypatch.setattr(p, "save", fail)
    with pytest.raises(OSError, match="planning save"):
        plan_design(p, lambda *args: action, "Make it 8 mm thick")
    assert (p.requirements, p.stage, p.clarification) == before
    assert not p.revisions and p.last_planner_attempt["error"] == p.error


def test_interrupted_snapshot_recovers_without_replaying_work_and_rejects_dangling_revision(
    project,
):
    p = project
    p.generate()
    path = ROOT / "artifacts" / p.id / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["stage"] = "checking"
    path.write_text(json.dumps(data), encoding="utf-8")
    restored = Project.load(path)
    assert restored.current == p.current and "interrupted" in restored.error
    assert len(restored.revisions) == 1
    data["active_id"] = "unknown"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="active revision"):
        Project.load(path)


@pytest.mark.parametrize(
    "error,questions,phase,index",
    [
        (None, (), DesignPhase.READY, 2),
        (None, ("Choose a face",), DesignPhase.CLARIFYING, 1),
        ("Failed", (), DesignPhase.RECOVERY, 2),
        ("Failed", ("Choose a face",), DesignPhase.RECOVERY, 1),
    ],
)
def test_header_and_conversation_share_phase(error, questions, phase, index):
    p = SimpleNamespace(current=None, error=error)
    state = workflow_state(p, questions)
    assert state.phase == phase and presentation(state)[2] == index


def test_workspace_modes_are_exclusive_scoped_and_reject_unknown_events(monkeypatch):
    from fixture import workspace
    from fixture.lifecycle import WorkspaceMode

    class Session(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__

    session = Session()
    monkeypatch.setattr(workspace.st, "session_state", session)
    p = SimpleNamespace(id="first")
    flags = ("face_mode", "pick_mode", "access_mode", "opening_mode")
    for mode in WorkspaceMode:
        workspace.set_workspace_mode(mode, p)
        assert workspace.workspace_mode(p) == mode
        assert sum(session[key] for key in flags) == (mode != WorkspaceMode.ASSEMBLY)
    previous = dict(session)
    with pytest.raises(ValueError):
        workspace.set_workspace_mode("unknown", p)
    assert session == previous
    assert (
        workspace.workspace_mode(SimpleNamespace(id="second")) == WorkspaceMode.ASSEMBLY
    )
    assert not any(session[key] for key in flags)


def test_failed_intake_does_not_replace_current_project(monkeypatch):
    from streamlit.testing.v1 import AppTest

    a, r = ready()
    previous = Project(a, r)
    ui = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45)
    ui.session_state.project = previous
    ui.run()

    def fail_save(self):
        raise OSError("Injected intake save failure")

    monkeypatch.setattr(Project, "save", fail_save)
    next(b for b in ui.button if b.label == "Load example").click().run()
    assert not ui.exception
    assert ui.session_state.project is previous
    assert any("intake save failure" in error.value for error in ui.error)
