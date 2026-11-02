import json

import pytest

from fixture.design_brief import save_brief, started
from fixture.project import Project
from fixture.planning import missing_questions, patch_requirements
from fixture.agent import Action, Changes, apply_action, planner_context
from fixture.workflow import plan_design
from tests.test_geometry import ready, ROOT


def test_guided_context_is_asked_first_and_saved_for_planner_and_resume():
    a, _ = ready()
    p = Project.new(a)
    assert not started(p)
    save_brief(p, "Hold a motor for bench testing", {"quantity": 1})
    assert started(p) and not p.revisions
    questions = missing_questions(a, p.requirements)
    assert "move or rotate" in questions[0]
    assert "tools" in questions[1] and "loads" in questions[2]
    assert not any("cable" in q.lower() for q in questions)
    assert "Cable routing:" not in p.messages[-1]["content"]
    text = save_brief(
        p,
        "Hold a motor for bench testing",
        {
            "quantity": 1,
            "moving_components": "Propeller rotates; body is fixed",
            "cable_routing": "Three wires exit the rear; route below",
            "service_access": "Hex key access to the mounting screws",
            "motion_loads": "Bidirectional thrust; value unknown",
        },
    )
    context = planner_context(a, p.requirements)
    assert context["requirements"]["cable_routing"].startswith("Three wires")
    assert "Hex key" in p.requirements.access
    assert p.messages[-1]["content"] == text
    save_brief(p, "Updated bench test", {"service_access": "Front hex key access"})
    assert p.requirements.cable_routing == "Three wires exit the rear; route below"
    assert "Cable routing: Three wires" in p.messages[-1]["content"]
    restored = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert restored.requirements == p.requirements and started(restored)


def test_cable_routing_is_not_required_for_initial_proposal_or_legacy_access():
    a, r = ready(moving_components="None", service_access="Front tools")
    p = Project(a, r)
    save_brief(p, "Hold for inspection", {})
    assert p.requirements.cable_routing is None
    assert not missing_questions(a, p.requirements)
    assert p.stage == "proposing"
    legacy_questions = missing_questions(a, r.model_copy(update={"access": None}))
    assert any("service access" in q for q in legacy_questions)
    assert not any("cable" in q.lower() for q in legacy_questions)


def test_unknown_is_explicit_blank_is_not_no_and_edits_honor_locks(monkeypatch):
    a, r = ready()
    p = Project(a, r)
    save_brief(
        p,
        "Inspection",
        {
            "moving_components": "unknown",
            "cable_routing": "None",
            "service_access": "",
            "motion_loads": "unknown",
        },
    )
    assert p.requirements.service_access is None
    assert any("tools" in q for q in missing_questions(a, p.requirements))
    assert not any("move or rotate" in q for q in missing_questions(a, p.requirements))
    before = p.requirements
    p.requirements = p.requirements.model_copy(update={"locks": ("cable_routing",)})
    with pytest.raises(ValueError, match="locked"):
        save_brief(p, "Inspection", {"cable_routing": "add wire channel"})
    assert p.requirements.cable_routing == before.cable_routing
    with pytest.raises(ValueError, match="Describe"):
        save_brief(p, "", {})
    with pytest.raises(ValueError, match="Unknown design"):
        save_brief(p, "Inspection", {"thickness": 12})


def test_failed_brief_save_rolls_back_everything(monkeypatch):
    a, r = ready()
    p = Project(a, r)
    p.last_planner_attempt = {"action": {"questions": ["Old question"]}}
    before = (p.requirements, p.stage, list(p.messages), p.last_planner_attempt)

    def fail():
        raise OSError("Injected save failure")

    monkeypatch.setattr(p, "save", fail)
    with pytest.raises(OSError):
        save_brief(p, "New task", {"quantity": 3})
    assert (p.requirements, p.stage, p.messages, p.last_planner_attempt) == before


def test_answer_edits_update_access_and_pending_questions_stop_build():
    a, r = ready(cable_routing="Old wires", service_access="Driver access")
    candidate = apply_action(
        a,
        r,
        Action(
            action="clarify",
            changes=Changes(cable_routing="No cables"),
            questions=("What is the rotating disc diameter?",),
            highlight_ids=(),
            explanation="Confirm its clearance.",
        ),
    )
    assert "Old wires" not in candidate.access and "Driver access" in candidate.access
    p = Project(a, candidate)
    action = Action(
        action="build",
        changes=Changes(),
        questions=("Disc diameter?",),
        highlight_ids=(),
        explanation="Need its swept space.",
    )
    assert not plan_design(p, lambda *args: action, "Build it")
    assert p.stage == "clarifying" and not p.revisions
    assert p.last_planner_attempt["action"]["questions"] == ["Disc diameter?"]
    unlocked = patch_requirements(candidate, {"service_access": "None"})
    assert "Driver access" not in unlocked.access


def test_resume_preserves_completed_legacy_design_and_explicit_clarification():
    from fixture.ui_theme import conversation_questions

    a, r = ready()
    p = Project(a, r)
    p.generate()
    p.last_planner_attempt = {"action": {"questions": ["An earlier question"]}}
    p.save()
    path = ROOT / "artifacts" / p.id / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("stage")
    path.write_text(json.dumps(data), encoding="utf-8")
    restored = Project.load(path)
    assert restored.stage == "presented" and restored.current.id == p.current.id
    assert not conversation_questions(restored)

    data["stage"] = "clarifying"
    path.write_text(json.dumps(data), encoding="utf-8")
    restored = Project.load(path)
    assert conversation_questions(restored) == ("An earlier question",)

    data.pop("stage")
    data.update(active_id=None, revisions=[])
    path.write_text(json.dumps(data), encoding="utf-8")
    restored = Project.load(path)
    assert restored.stage == "clarifying" and not restored.current
    assert conversation_questions(restored) == ("An earlier question",)
