import io
import zipfile
import pytest
from fixture.contracts import Envelope
from fixture.planning import compile_plan, patch_requirements
from fixture.executor import execute
from fixture.validation import validate
from fixture.project import Project
from fixture.review import render_review
from tests.test_geometry import ready


@pytest.mark.parametrize("kind", ["l_bracket", "bridge"])
@pytest.mark.parametrize(
    "source,diameter",
    [
        ("synthetic_motor.step", 3.5),
        ("sensor_bracket.step", 4.5),
        ("transformed_motor.step", 3.5),
    ],
)
def test_structures_preserve_measured_patterns_and_perpendicular_feet(
    kind, source, diameter, tmp_path
):
    a, r = ready(
        source,
        composition=kind,
        clearance_diameter=diameter,
        surroundings="bolt",
        bench_hole_diameter=3.2,
        mount_height=70.0,
    )
    plan = compile_plan(a, r)
    bodies, meshes, cuts = execute(plan, a, tmp_path / "fixture.usda")
    checks = validate(a, r, plan, bodies, cuts)
    assert not [c for c in checks if c.result == "failed"]
    assert len(bodies) == 1
    assert next(iter(bodies.values())).material_census()["solid_count"] == 1
    assert len(cuts) == (3 if source == "sensor_bracket.step" else 4)
    assert plan.parameters["mount_height_mm"] == 70.0
    assert all(
        c.result == "passed" for c in checks if c.name.startswith("Base fastener")
    )
    assert all(len(m.triangles) > 0 for m in meshes.values())
    expected_axis = "y" if kind == "l_bracket" else "z"
    assert {op.axis for op in plan.operations if "-bench-" in op.id} == {expected_axis}
    assert (
        f'upAxis = "{expected_axis.upper()}"' in (tmp_path / "fixture.usda").read_text()
    )


def test_l_bracket_ribs_opening_revision_export_and_restore(tmp_path):
    a, r = ready(composition="l_bracket", mount_height=70.0, base_depth=40.0)
    p = Project(a, r)
    first = p.generate()
    images = render_review(a, first)
    assert images[0].exists()
    env = Envelope(
        id="wire", minimum=(-4, -4, -8), maximum=(4, 4, 1), purpose="Wire routing"
    )
    second = p.generate(
        patch_requirements(r, {"reinforce": False, "envelopes": (env,)}),
        "Remove ribs and add wire opening",
    )
    assert second.parent == first.id
    assert second.metrics["volume_mm3"] < first.metrics["volume_mm3"]
    assert all(c.result != "failed" for c in second.checks)
    archive = tmp_path / "fixture.zip"
    archive.write_bytes(p.export())
    from scripts.reproduce import reproduce

    reproduce(archive, tmp_path / "rebuilt")
    with zipfile.ZipFile(io.BytesIO(p.export())) as z:
        assert b"l_bracket" in z.read("plan.json")
    p.restore(first.id)
    assert p.requirements.reinforce and p.current.id == first.id
    with pytest.raises(ValueError, match="locked"):
        patch_requirements(
            r.model_copy(update={"locks": ("mount_height",)}), {"mount_height": 80}
        )


def test_bridge_grid_and_full_width_constraint(tmp_path):
    a, r = ready(composition="bridge", quantity=4, layout="grid", columns=2)
    plan = compile_plan(a, r)
    bodies, _, cuts = execute(plan, a, tmp_path / "bridge.usda")
    assert len(cuts) == 16 and len(bodies) == 1
    assert all(c.result != "failed" for c in validate(a, r, plan, bodies, cuts))
    with pytest.raises(ValueError, match="including base feet"):
        compile_plan(
            a, patch_requirements(r, {"max_width": plan.parameters["width_mm"] - 1})
        )
    with pytest.raises(ValueError, match="height"):
        compile_plan(a, patch_requirements(r, {"mount_height": 5}))


def test_missing_native_base_holes_are_detected(tmp_path):
    a, r = ready(composition="l_bracket", surroundings="bolt", bench_hole_diameter=3.2)
    plan = compile_plan(a, r)
    uncut = plan.model_copy(
        update={
            "operations": tuple(op for op in plan.operations if "-bench-" not in op.id)
        }
    )
    bodies, _, cuts = execute(uncut, a, tmp_path / "uncut.usda")
    results = validate(a, r, plan, bodies, cuts)
    assert (
        next(c for c in results if c.name == "Base fastener geometry").result
        == "failed"
    )


def test_measured_rear_relief_and_clearance_larger_than_thread(tmp_path):
    # Synthetic source with a rear shaft: application still measures the STEP.
    import cadquery as cq
    from fixture.intake import analyze_file, local_points

    source = cq.importers.importStep("samples/synthetic_motor.step").union(
        cq.Workplane("XY").circle(3).extrude(-8)
    )
    path = tmp_path / "rear-shaft.step"
    cq.exporters.export(source, str(path))
    a = analyze_file(path)
    i = next(
        i
        for i in a.interfaces
        if len(i.hole_ids) == 5 and abs(i.origin[2]) < 0.01 and i.z[2] > 0.9
    )
    # The shaft opening is explicitly excluded by the synthetic test user.
    holes = tuple(h for h, d in zip(i.hole_ids, i.diameters) if abs(d - 4) < 0.01)
    assert len(holes) == 4 and local_points(a.mesh.vertices, i)[:, 2].min() < -7.9
    _, r = ready(
        composition="l_bracket",
        interface_id=i.id,
        mounting_hole_ids=holes,
        clearance_diameter=4.2,
    )
    plan = compile_plan(a, r)
    assert plan.parameters["rear_relief"] == "separate measured profiles"
    bodies, _, cuts = execute(plan, a, tmp_path / "relieved.usda")
    assert all(c.result != "failed" for c in validate(a, r, plan, bodies, cuts))
    assert len(cuts) == 4
