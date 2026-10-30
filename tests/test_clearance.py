import numpy as np
import pytest
from fixture.contracts import Operation
from fixture.intake import analyze_file
from fixture.planning import compile_plan, patch_requirements
from fixture.project import Project
from fixture.executor import execute, primitive
from fixture.validation import validate
from fixture.clearance import rear_regions, footprint_distance
from tests.test_geometry import ready


def protruding_source(tmp_path):
    import cadquery as cq

    part = cq.importers.importStep("samples/synthetic_motor.step")
    part = part.union(cq.Workplane("XY").circle(3).extrude(-8))
    part = part.union(
        cq.Workplane("XY")
        .center(-24, -20)
        .box(6, 6, 8, centered=(True, True, False))
        .translate((0, 0, -8))
    )
    path = tmp_path / "separate-protrusions.step"
    cq.exporters.export(part, str(path))
    a = analyze_file(path)
    i = next(
        i
        for i in a.interfaces
        if abs(i.origin[2]) < 0.01 and i.z[2] > 0.9 and len(i.hole_ids) >= 4
    )
    holes = tuple(
        h
        for h, d, valid in zip(i.hole_ids, i.diameters, i.contact_valid)
        if abs(d - 4) < 0.01 and valid
    )
    assert len(holes) == 4
    _, r = ready(composition="l_bracket", interface_id=i.id, mounting_hole_ids=holes)
    return a, r, i


def test_separate_clearances_preserve_mounting_and_reproduce(tmp_path):
    a, r, i = protruding_source(tmp_path)
    with pytest.raises(ValueError, match="conflicts with contact"):
        compile_plan(a, r, compiler_version=1)
    p = Project(a, r)
    rev = p.generate()
    regions = [op for op in rev.plan.operations if op.id.startswith("rear-relief-")]
    assert rev.plan.version == 8 and len(regions) == 2
    assert {op.shape for op in regions} == {"cylinder", "prism"}
    assert rev.metrics["hole_count"] == 4 and rev.metrics["body_count"] == 1
    assert all(c.result == "passed" for c in rev.checks if c.name.startswith("Rear"))
    assert all(c.result != "failed" for c in rev.checks)
    from fixture.viewer import assembly_figure

    preview = assembly_figure(a, i.id, rev, envelopes=True)
    visible_regions = [t for t in preview.data if t.name == "Measured rear clearance"]
    assert len(visible_regions) == 2
    assert sum(bool(t.showlegend) for t in visible_regions) == 1
    assert not any(
        t.name == "Measured rear clearance"
        for t in assembly_figure(a, i.id, rev, envelopes=False).data
    )
    previous_volume = rev.metrics["volume_mm3"]
    second = p.generate(
        patch_requirements(r, {"rear_clearance": 0.8}),
        "Increase measured rear clearance",
    )
    assert second.parent == rev.id and second.metrics["volume_mm3"] < previous_volume
    assert second.requirements.mounting_hole_ids == r.mounting_hole_ids
    archive = tmp_path / "enhanced.zip"
    archive.write_bytes(p.export())
    from scripts.reproduce import reproduce

    reproduce(archive, tmp_path / "reproduced")


def test_conflicting_clearance_and_locks_preserve_last_valid(tmp_path):
    a, r, _ = protruding_source(tmp_path)
    p = Project(a, r)
    rev = p.generate()
    with pytest.raises(ValueError, match="overlaps support"):
        p.generate(patch_requirements(r, {"rear_clearance": 5.0}))
    assert p.current.id == rev.id and p.requirements == r
    with pytest.raises(ValueError, match="locked"):
        patch_requirements(
            r.model_copy(update={"locks": ("rear_clearance",)}), {"rear_clearance": 0.8}
        )


def test_missing_or_uncut_rear_regions_fail_validation(tmp_path):
    a, r, _ = protruding_source(tmp_path)
    plan = compile_plan(a, r)
    # Remove clearance ops and rebuild their dependency chain to represent a
    # valid but incorrect plan. Check both record omission and material omission.
    ops = []
    for op in plan.operations:
        if op.id.startswith("rear-relief-"):
            continue
        ops.append(op.model_copy(update={"depends_on": (ops[-1].id,) if ops else ()}))
    missing = plan.model_copy(update={"operations": tuple(ops)})
    bodies, _, cuts = execute(missing, a, tmp_path / "uncut.usda")
    checks = validate(a, r, missing, bodies, cuts)
    assert (
        next(c for c in checks if c.name == "Rear clearance coverage").result
        == "failed"
    )
    checks = validate(a, r, plan, bodies, cuts)
    assert any(
        c.name.startswith("Rear protrusion clearance") and c.result == "failed"
        for c in checks
    )


def test_envelopes_cover_clipped_mesh_and_keep_separate_gaps(tmp_path):
    a, r, i = protruding_source(tmp_path)
    from fixture.intake import local_points

    points = local_points(a.mesh.vertices, i)
    regions = rear_regions(a, i, r.rear_clearance)
    assert len(regions) == 2
    for point in points[points[:, 2] < -0.01]:
        assert any(
            op.origin[2] <= point[2] <= op.origin[2] + op.size[2]
            and footprint_distance(op, point) < 1e-6
            for op in regions
        )
    assert all(
        footprint_distance(op, i.centers[i.hole_ids.index(r.mounting_hole_ids[0])]) > 0
        for op in regions
    )


def test_bounded_prism_contract_and_native_sweep():
    values = dict(
        id="profile",
        kind="relief",
        shape="prism",
        size=(5, 6, 4),
        profile=((0, 0), (5, 0), (4, 6), (0, 4)),
        provenance={"profile": "measured"},
    )
    body = primitive(Operation(**values))
    assert body.is_manifold_solid() and body.volume(1e-7) == pytest.approx(92)
    for bad in [
        ((0, 0), (5, 0), (2, 1), (4, 6), (0, 4)),
        ((0, 0), (5, 6), (0, 6), (5, 0)),
        ((0, 0), (5000, 0), (0, 4)),
    ]:
        with pytest.raises(ValueError):
            Operation(**{**values, "profile": bad})
    with pytest.raises(ValueError):
        Operation(
            **{**values, "profile": tuple((float(x), float(x * x)) for x in range(50))}
        )


def test_legacy_structure_export_still_reproduces(tmp_path):
    from scripts.reproduce import reproduce

    reproduce("demo/live-l_bracket-export.zip", tmp_path / "legacy")


def test_regions_follow_rigid_source_transform(tmp_path):
    a, r, i = protruding_source(tmp_path)
    rotation = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]], dtype=float)
    shift = np.array([70, -31, 42])
    moved_i = i.model_copy(
        update={
            "origin": tuple(rotation @ i.origin + shift),
            **{
                axis: tuple(rotation @ np.array(getattr(i, axis)))
                for axis in ("x", "y", "z")
            },
            "source_to_local": tuple(
                tuple(row) for row in np.eye(4)
            ),  # Distinct cache frame in test.
        }
    )
    moved = a.model_copy(
        update={
            "mesh": a.mesh.model_copy(
                update={
                    "vertices": tuple(
                        map(tuple, np.array(a.mesh.vertices) @ rotation.T + shift)
                    )
                }
            )
        }
    )
    expected = rear_regions(a, i, r.rear_clearance)
    actual = rear_regions(moved, moved_i, r.rear_clearance)
    assert len(actual) == len(expected)
    for left, right in zip(expected, actual):
        assert left.shape == right.shape
        assert left.origin == pytest.approx(right.origin, abs=1e-6)
        assert left.size == pytest.approx(right.size, abs=1e-6)
