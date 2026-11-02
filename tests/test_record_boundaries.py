"""Equivalent records from distinct module loads must cross workflow boundaries."""

import importlib.util
import sys

import pytest

from fixture import workflow
from fixture.agent import Action, Changes
from fixture.contracts import DesignReview, RepairChanges
from fixture.project import Project, ROOT
from tests.test_geometry import ready


@pytest.fixture
def reloaded_contracts(monkeypatch):
    name = "fixture._contracts_reload_test"
    spec = importlib.util.spec_from_file_location(name, ROOT / "fixture/contracts.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def test_revision_feedback_accepts_equivalent_build_record_after_reload(
    monkeypatch, reloaded_contracts
):
    a, r = ready(quantity=4, layout="row")
    p = Project(a, r)
    previous = p.generate()
    # Reproduce the reported same-name/different-class rejection exactly.
    with pytest.raises(ValueError, match="BuildFeedback"):
        reloaded_contracts.FeedbackRecord(
            run_id="probe",
            attempt=1,
            provider="test",
            build=p.last_attempt,
            outcome="offline",
        )
    monkeypatch.setattr(workflow, "FeedbackRecord", reloaded_contracts.FeedbackRecord)
    candidate = r.model_copy(update={"layout": "grid", "columns": 2})
    revised = workflow.generate_with_feedback(
        p, None, "Offline", candidate, "Change four parts to a 2 by 2 grid"
    )
    assert revised.id != previous.id and p.error is None
    assert revised.plan.parameters["quantity"] == 4
    assert len({pos[0] for pos in revised.plan.placements}) == 2
    assert len({pos[1] for pos in revised.plan.placements}) == 2
    assert p.feedback[-1].build.revision_id == revised.id
    restored = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert (
        restored.current.id == revised.id and restored.feedback[-1].outcome == "offline"
    )


def test_provider_review_can_cross_model_class_boundary(
    monkeypatch, reloaded_contracts
):
    a, r = ready()
    p = Project(a, r)
    monkeypatch.setattr(workflow, "DesignReview", reloaded_contracts.DesignReview)
    review = DesignReview(
        verdict="accept",
        summary="Geometry checked",
        findings=(),
        changes=RepairChanges(),
        questions=(),
    )
    result = workflow.generate_with_feedback(p, lambda *args: review, "Test provider")
    assert result and p.feedback[-1].outcome == "accepted"


def test_planner_boundary_validates_data_not_provider_class_identity(monkeypatch):
    action = Action(
        action="propose",
        changes=Changes(gap=14),
        questions=(),
        highlight_ids=(),
        explanation="Use 14 mm spacing.",
    )
    # Inspect the validator's input rather than accepting an unvalidated object.
    native_validate = Action.model_validate
    seen = []

    def validate(value):
        seen.append(value)
        assert isinstance(value, dict)
        return native_validate(value)

    monkeypatch.setattr(workflow.Action, "model_validate", validate)
    a, r = ready()
    p = Project(a, r)
    assert not workflow.plan_design(p, lambda *args: action, "Use 14 mm spacing")
    assert seen and p.requirements.gap == 14


def test_app_uses_explicit_restart_for_typed_cad_sessions():
    import tomllib

    config = tomllib.loads((ROOT / ".streamlit/config.toml").read_text())
    assert config["server"]["fileWatcherType"] == "none"
