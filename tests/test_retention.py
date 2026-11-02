from pathlib import Path
from types import SimpleNamespace
import numpy as np
import cadquery as cq
import pytest
from fixture.contracts import Requirements
from fixture.intake import analyze_file, local_points, selected_interface
from fixture.face_picking import FacePicks, use_picked_face
from fixture.planning import (
    compile_plan,
    patch_requirements,
    missing_questions,
    proposals,
)
from fixture.project import Project
from fixture.step_export import prepare_step
from fixture.executor import execute
from fixture.validation import validate


def ready():
    a = analyze_file("samples/hole_free_housing.step")
    i = next(i for i in a.interfaces if i.z[2] > 0.99 and abs(i.origin[2]) < 0.01)
    r = Requirements(
        purpose="Bench inspection",
        quantity=1,
        interface_id=i.id,
        mounting_confirmed=True,
        part_attachment="cradle",
        motion_loads="Resting upright; no moving loads",
        access="Top must remain open",
        surroundings="bolt",
        bench_fastener="M3",
        bench_hole_count=4,
        fabrication="3D printing",
        assumptions_accepted=True,
    )
    return a, r


def test_all_planar_faces_and_no_invented_mounting_pattern():
    a, r = ready()
    assert len(a.interfaces) >= 6 and all(not i.hole_ids for i in a.interfaces)
    pending = use_picked_face(
        a, Requirements(), FacePicks(interface_id=r.interface_id), (), True
    )
    assert pending.mounting_confirmed and pending.part_attachment == "unselected"
    assert any(
        "retain" in q
        for q in missing_questions(
            a, pending.model_copy(update={"purpose": "Inspect", "quantity": 1})
        )
    )
    with pytest.raises(ValueError, match="retain"):
        compile_plan(a, pending, require_ready=False)
    assert all(p.composition == "plate" for p in proposals(a, r))
    with pytest.raises(ValueError, match="version 8"):
        compile_plan(a, r, compiler_version=7)
    with pytest.raises(ValueError, match="base screw"):
        compile_plan(
            a, r.model_copy(update={"bench_fastener": None}), require_ready=False
        )
    with pytest.raises(ValueError, match="strap width"):
        compile_plan(
            a, r.model_copy(update={"part_attachment": "strap"}), require_ready=False
        )


@pytest.mark.parametrize(
    "attachment,quantity", [("cradle", 1), ("strap", 1), ("strap", 2)]
)
def test_real_trays_step_revision_and_no_part_holes(tmp_path, attachment, quantity):
    a, r = ready()
    r = r.model_copy(
        update={
            "part_attachment": attachment,
            "quantity": quantity,
            "strap_width": 10,
            "strap_thickness": 1.5,
        }
    )
    project = Project(a, r)
    rev = project.generate()
    assert (
        rev.plan.version == 12
        and rev.metrics["hole_count"] == 0
        and rev.metrics["base_hole_count"] == 4
    )
    assert not any(c.result == "failed" for c in rev.checks)
    assert (
        next(c for c in rev.checks if c.name == "Part retention").result
        == "not_evaluated"
    )
    assert not any(op.kind == "mount" for op in rev.plan.operations)
    step = prepare_step(rev)
    solid = cq.importers.importStep(str(step)).val()
    assert solid.isValid() and len(solid.Solids()) == 1
    slots = [op for op in rev.plan.operations if op.id.startswith("strap-slot")]
    assert len(slots) == (2 * quantity if attachment == "strap" else 0)
    for op in slots:
        probe = (
            cq.Workplane("XY")
            .box(*op.size, centered=(False, False, False))
            .translate(op.origin)
            .val()
        )
        assert solid.intersect(probe).Volume() < 0.01
    if attachment == "cradle":
        updated = project.generate(
            patch_requirements(r, {"locating_clearance": 1}), "More insertion clearance"
        )
        assert updated.parent == rev.id
        assert updated.plan.parameters["width_mm"] > rev.plan.parameters["width_mm"]
        project.restore(rev.id)
        assert project.requirements == r
        with pytest.raises(ValueError, match="locked"):
            patch_requirements(
                r.model_copy(update={"locks": ("part_attachment",)}),
                {"part_attachment": "strap"},
            )


def test_missing_wall_or_blind_strap_slot_fails_native_checks(tmp_path):
    a, r = ready()
    r = r.model_copy(
        update={"part_attachment": "strap", "strap_width": 10, "strap_thickness": 1.5}
    )
    plan = compile_plan(a, r)
    for fault in ("wall", "slot"):
        ops = []
        for op in plan.operations:
            if fault == "wall" and op.id == "locating-wall-0-0":
                op = op.model_copy(update={"size": (*op.size[:2], 0.2)})
            if fault == "slot" and op.id == "strap-slot-0-0":
                op = op.model_copy(update={"size": (*op.size[:2], 2.0)})
            ops.append(op)
        damaged = plan.model_copy(update={"operations": tuple(ops)})
        bodies, _, cuts = execute(damaged, a, tmp_path / (fault + ".usda"))
        checks = validate(a, r, damaged, bodies, cuts)
        assert any(
            c.result == "failed"
            and c.name == ("Locating walls" if fault == "wall" else "Strap passages")
            for c in checks
        )


def test_transformed_hole_free_frame(tmp_path):
    a, r = ready()
    part = (
        cq.importers.importStep("samples/hole_free_housing.step")
        .rotate((0, 0, 0), (1, 2, 3), 37)
        .translate((81, -12, 34))
    )
    path = tmp_path / "transformed.step"
    cq.exporters.export(part, str(path))
    b = analyze_file(path)
    ia = selected_interface(a, r)
    ib = next(i for i in b.interfaces if i.id == ia.id)
    assert np.ptp(local_points(a.mesh.vertices, ia), axis=0) == pytest.approx(
        np.ptp(local_points(b.mesh.vertices, ib), axis=0), abs=0.001
    )
    assert compile_plan(a, r).parameters["width_mm"] == pytest.approx(
        compile_plan(b, r).parameters["width_mm"], abs=0.001
    )


def test_ui_selects_a_face_without_holes_immediately(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(
        "fixture.mounting_picker.picker_component",
        lambda: lambda **kw: SimpleNamespace(picked=None),
    )
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45
    ).run()
    next(s for s in app.selectbox if s.label == "Bundled specimen").select(
        "hole_free_housing.step"
    ).run()
    next(b for b in app.button if b.label == "Load example").click().run()
    next(b for b in app.button if b.label == "Select mounting face").click().run()
    a, r = ready()
    next(s for s in app.selectbox if s.label == "Mounting face").select(
        r.interface_id
    ).run()
    assert not app.exception
    assert app.session_state["project"].requirements.mounting_confirmed
    assert not app.session_state["project"].requirements.mounting_hole_ids
    assert app.session_state["project"].requirements.part_attachment == "unselected"
    next(s for s in app.selectbox if s.label == "How should the part be held?").select(
        "cradle"
    ).run()
    next(b for b in app.button if b.label == "Apply part retention").click().run()
    assert (
        not app.exception
        and app.session_state["project"].requirements.part_attachment == "cradle"
    )
    assert not any("Proposed screw size" in str(m.value) for m in app.markdown)
