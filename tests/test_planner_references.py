"""Measured access IDs must round-trip through planning without becoming CAD code."""

import json
import cadquery as cq
import pytest

from fixture.agent import (
    Action,
    Changes,
    apply_action,
    feature_references,
    planner_context,
)
from fixture.contracts import AccessSelection, HardwareChoice
from fixture.intake import analyze_file
from fixture.planning import missing_questions, proposals
from fixture.project import Project, ROOT
from fixture.step_export import prepare_step
from fixture.workflow import plan_design
from tests.test_geometry import ready
from tests.test_passages import shallow_source


def decision(ids=(), **changes):
    return Action(
        action="propose",
        changes=Changes(**changes),
        highlight_ids=ids,
        questions=(),
        explanation="Use the measured opening and selected screws.",
    )


def test_every_offered_access_reference_is_a_valid_highlight(tmp_path):
    a, r, rear = shallow_source(tmp_path)
    context = planner_context(a, r)
    choices = context["access_options"]
    assert {c["kind"] for c in choices} == {"hole", "face", "rear"}
    assert "rear:" + rear in context["valid_highlight_ids"]
    for choice in choices:
        ref = choice["feature_id"]
        assert ref in context["valid_highlight_ids"]
        assert apply_action(a, r, decision((ref,))) == r
    # Older raw IDs still work alongside access namespaces.
    for ref in (r.interface_id, r.mounting_hole_ids[0], rear):
        assert apply_action(a, r, decision((ref,))) == r
    assert "M3" in context["hardware_profiles"]["countersink"]
    assert "M16" not in context["hardware_profiles"]["countersink"]


@pytest.mark.parametrize(
    "ref", ["made-up", "hole:made-up", "face:made-up", "rear-relief-0"]
)
def test_unknown_highlights_still_rejected_with_the_offending_id(ref):
    a, r = ready()
    with pytest.raises(ValueError, match="unknown feature: " + ref):
        apply_action(a, r, decision((ref,)))


@pytest.mark.parametrize("namespaced", [False, True])
def test_access_requires_a_real_namespaced_reference(namespaced):
    a, r = ready()
    face = next(i for i in a.interfaces if i.id == r.interface_id)
    ref = "hole:invented" if namespaced else face.hole_ids[0]
    with pytest.raises(ValueError, match="unknown access feature: " + ref):
        apply_action(
            a, r, decision(access_selections=(AccessSelection(feature_id=ref),))
        )


def test_lock_error_is_not_hidden_by_a_highlight_error():
    a, r = ready(locks=("thickness",))
    with pytest.raises(ValueError, match="thickness is locked"):
        apply_action(a, r, decision(("made-up",), thickness=9))


def test_rear_measurement_error_does_not_erase_measured_hole_references(monkeypatch):
    a, r = ready()
    hole = next(i for i in a.interfaces if i.id == r.interface_id).hole_ids[0]

    def fail(*args):
        raise ValueError("Cannot infer rear profile")

    monkeypatch.setattr("fixture.clearance.passage_options", fail)
    assert feature_references(a, r)["hole:" + hole] == hole
    assert apply_action(a, r, decision(("hole:" + hole,))) == r


def test_failed_decision_is_saved_and_retry_preserves_existing_cad():
    a, r = ready()
    p = Project(a, r)
    previous = p.generate()
    bad = decision(("hole:made-up",), quantity=3)
    assert not plan_design(p, lambda *args: bad, text="Try this change")
    assert p.requirements == r and p.current.id == previous.id
    assert p.last_planner_attempt["action"] == bad.model_dump(mode="json")
    assert "hole:made-up" in p.last_planner_attempt["error"]
    assert "Planning failed" in p.messages[-1]["content"]
    assert "No design changes were applied" in p.messages[-1]["content"]
    restored = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert restored.last_planner_attempt == p.last_planner_attempt
    assert restored.current.id == previous.id

    face = next(i for i in a.interfaces if i.id == r.interface_id)
    good = decision(("hole:" + face.hole_ids[0],), quantity=2)
    assert not plan_design(restored, lambda *args: good, start=True)
    assert restored.requirements.quantity == 2 and restored.error is None
    assert restored.last_planner_attempt["error"] is None
    assert restored.highlights == (face.hole_ids[0],)
    assert len(restored.revisions) == 1 and restored.current.id == previous.id


def test_malformed_response_diagnostics_and_old_project_compatibility():
    a, r = ready()
    p = Project(a, r)
    assert not plan_design(p, lambda *args: {"not": "an action"})
    assert p.last_planner_attempt["action"] is None
    assert "ValidationError" in p.last_planner_attempt["error"]
    path = ROOT / "artifacts" / p.id / "project.json"
    data = json.loads(path.read_text())
    data.pop("last_planner_attempt")
    path.write_text(json.dumps(data), encoding="utf-8")
    assert Project.load(path).last_planner_attempt is None


def test_start_design_ui_accepts_access_highlight_and_free_floating(monkeypatch):
    from streamlit.testing.v1 import AppTest

    calls = []

    def planner(a, r, *args):
        calls.append(r.interface_id)
        return decision(("face:" + r.interface_id,), surroundings="none")

    monkeypatch.setattr("fixture.subscription.subscription_turn", planner)
    ui = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    next(b for b in ui.button if b.label == "Load example").click().run()
    next(s for s in ui.selectbox if s.label == "Conversation mode").select(
        "ChatGPT subscription (Codex CLI)"
    ).run()
    next(b for b in ui.button if b.label == "Start design").click().run()
    p = ui.session_state["project"]
    assert not ui.exception and not p.error and len(calls) == 1
    attachment = next(
        s for s in ui.selectbox if s.label == "Attachment to surroundings"
    )
    assert attachment.value == "none" and "None — free floating" in attachment.options
    assert p.highlights == (p.requirements.interface_id,)
    assert p.last_planner_attempt["error"] is None and not p.revisions
    ui.run()
    assert len(calls) == 1  # Rerendering must not resubmit the model request.


def test_free_floating_two_bolt_fixture_has_countersinks_and_through_shaft_opening(
    tmp_path,
):
    # Synthetic source only; the real user's STEP is not needed in the public suite.
    source = (
        cq.Workplane("XY")
        .box(60, 40, 4, centered=(True, True, False))
        .faces(">Z")
        .workplane()
        .pushPoints([(-20, 0), (20, 0)])
        .hole(4)
        .faces(">Z")
        .workplane()
        .hole(20)
    )
    path = tmp_path / "two-bolt-flange.step"
    cq.exporters.export(source, str(path))
    a = analyze_file(path)
    face = next(i for i in a.interfaces if i.z[2] > 0.9 and len(i.hole_ids) == 3)
    mounts = tuple(h for h, d in zip(face.hole_ids, face.diameters) if d < 5)
    shaft = next(h for h, d in zip(face.hole_ids, face.diameters) if d > 10)
    _, r = ready(
        interface_id=face.id,
        mounting_hole_ids=mounts,
        nominal_fastener="M3",
        clearance_diameter=None,
    )
    p = Project(a, r)
    action = decision(
        ("hole:" + shaft,),
        surroundings="none",
        through_access_required=True,
        part_hardware=HardwareChoice(style="countersink"),
        access_selections=(AccessSelection(feature_id="hole:" + shaft),),
    )
    assert not plan_design(p, lambda *args: action, start=True)
    assert p.error is None and not missing_questions(a, p.requirements)
    assert p.requirements.mounting_hole_ids == mounts
    assert all(
        "No attachment" in prop.surroundings for prop in proposals(a, p.requirements)
    )
    rev = p.generate()
    assert rev.metrics["hole_count"] == 2 and rev.metrics["base_hole_count"] == 0
    assert rev.plan.parameters["hardware_seats"] == 2
    assert not any(c.result == "failed" for c in rev.checks)
    attachment = next(c for c in rev.checks if c.name == "Surrounding attachment")
    assert "No external attachment" in attachment.method
    assert attachment.result != "passed"
    shape = cq.importers.importStep(str(prepare_step(rev))).val()
    assert shape.isValid() and len(shape.Solids()) == 1
    center = face.centers[face.hole_ids.index(shaft)]
    probe = cq.Solid.makeCylinder(
        10, r.thickness + 2, cq.Vector(*center[:2], -r.thickness - 1)
    )
    assert shape.intersect(probe).Volume() < 0.001
