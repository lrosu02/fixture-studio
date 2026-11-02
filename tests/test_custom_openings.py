import math

import pytest

from fixture.contracts import FixtureOpening
from fixture.custom_openings import (
    opening_candidate,
    remove_opening,
    resize_opening,
    resolve_pick,
    opening_tools,
)
from fixture.planning import compile_plan, missing_questions
from fixture.project import Project
from tests.test_geometry import ready
from tests.test_sheet_metal import sheet


def event_at(revision, body, point):
    for n in range(len(revision.meshes[body].triangles)):
        event = dict(revision_id=revision.id, body=body, triangle=n, point=point)
        try:
            resolve_pick(revision, event)
            return event
        except ValueError:
            pass
    raise AssertionError(f"No surface at {point} on {body}")


def test_click_opening_resize_remove_step_and_reproduce(tmp_path):
    import cadquery as cq
    from fixture.step_export import prepare_step
    from scripts.reproduce import reproduce

    a, r = ready()
    p = Project(a, r)
    initial = p.generate()
    body = next(iter(initial.meshes))
    event = event_at(initial, body, (0, 0, 0))
    candidate = opening_candidate(p, event, 8)
    assert not p.requirements.fixture_openings and p.current is initial
    opened = p.generate(candidate, "Click a new 8 mm passage")
    assert opened.parent == initial.id and opened.plan.version == 14
    assert opened.metrics["hole_count"] == initial.metrics["hole_count"] == 4
    assert opened.metrics["fixture_opening_count"] == 1
    assert initial.metrics["volume_mm3"] - opened.metrics[
        "volume_mm3"
    ] == pytest.approx(math.pi * 4**2 * 6, abs=0.02)
    step = prepare_step(opened)
    shape = cq.importers.importStep(str(step)).val()
    assert all(s.isValid() for s in shape.Solids())
    assert (
        shape.intersect(cq.Workplane("XY").circle(4).extrude(-20).val()).Volume() < 0.01
    )
    archive = tmp_path / "opening.zip"
    archive.write_bytes(p.export(False))
    reproduce(archive, tmp_path / "rebuild")
    saved = p.requirements.fixture_openings[0]
    bigger = p.generate(resize_opening(p, saved.id, 10), "Resize passage")
    assert bigger.requirements.fixture_openings[0].center == saved.center
    thicker = p.generate(
        p.requirements.model_copy(update={"thickness": 8}), "Increase thickness"
    )
    assert not [c for c in thicker.checks if c.result == "failed"]
    restored = p.generate(remove_opening(p, saved.id), "Remove passage")
    assert not restored.requirements.fixture_openings
    assert restored.metrics["volume_mm3"] > thicker.metrics["volume_mm3"]
    p.restore(opened.id)
    assert p.requirements.fixture_openings[0].diameter == 8


@pytest.mark.parametrize(
    "construction,where",
    [("cut_weld", "wall"), ("bent_weld", "wall"), ("bent_weld", "base")],
)
def test_openings_in_welded_and_bent_sheet(construction, where):
    import usd_brep as sm

    a, r = sheet(sheet_construction=construction, base_depth=50)
    p = Project(a, r)
    initial = p.generate()
    point = (0, -30, 0) if where == "wall" else (0, -70, -30)
    candidate = opening_candidate(p, event_at(initial, "mounting-platform", point), 8)
    after = p.generate(candidate)
    assert not [c for c in after.checks if c.result == "failed"]
    assert after.metrics["body_count"] == initial.metrics["body_count"]
    assert after.metrics["base_hole_count"] == 4
    volumes = [
        sum(b.volume(relative_accuracy=1e-8) for b in sm.usd.import_breps(rev.artifact))
        for rev in (initial, after)
    ]
    assert volumes[0] - volumes[1] == pytest.approx(math.pi * 4**2 * 3, abs=0.01)


def test_opening_failures_preserve_last_valid_fixture():
    a, r = ready()
    p = Project(a, r)
    initial = p.generate()
    body = next(iter(initial.meshes))
    event = event_at(initial, body, (31, 0, 0))
    candidate = opening_candidate(p, event, 8)
    with pytest.raises(ValueError, match="edge"):
        p.generate(candidate)
    assert p.current.id == initial.id and p.requirements == r
    event = event_at(initial, body, (0, 0, 0))
    with pytest.raises(ValueError, match="older fixture"):
        opening_candidate(p, {**event, "revision_id": "stale"}, 8)
    with pytest.raises(ValueError, match="outside|surface"):
        resolve_pick(initial, {**event, "point": (100, 100, 0)})
    p.requirements = r.model_copy(update={"locks": ("fixture_openings",)})
    with pytest.raises(ValueError, match="locked"):
        opening_candidate(p, event, 8)
    with pytest.raises(ValueError):
        FixtureOpening(
            id="one", body=body, center=(0, 0, 0), axis="z", diameter=float("nan")
        )


def test_full_depth_validator_detects_a_blind_or_blocked_opening(tmp_path, monkeypatch):
    from fixture.executor import execute
    from fixture.validation import validate

    a, r = ready()
    opening = FixtureOpening(
        id="wire", body="stock-0", center=(0, 0, 0), axis="z", diameter=8
    )
    r = r.model_copy(update={"fixture_openings": (opening,)})
    plan = compile_plan(a, r)
    tool = opening_tools(r, plan)[0]
    ops = tuple(
        o.model_copy(update={"origin": (0, 0, -2), "size": (8, 8, 3)})
        if o.id == tool.id
        else o
        for o in plan.operations
    )
    blind = plan.model_copy(update={"operations": ops})
    with pytest.raises(ValueError, match="flat"):
        execute(blind, a, tmp_path / "rejected-blind.usda")
    # Fault injection bypasses the executor guard to exercise the independent
    # final-CAD validator, rather than weakening that guard for malformed plans.
    monkeypatch.setattr("fixture.custom_openings.check_cut", lambda *args: None)
    bodies, _, cuts = execute(blind, a, tmp_path / "blind.usda")
    checks = validate(a, r, blind, bodies, cuts)
    assert any(
        c.name.startswith("Fixture through opening") and c.result == "failed"
        for c in checks
    )
    assert any(
        c.name == "Fixture opening schedule" and c.result == "failed" for c in checks
    )


def test_deferred_openings_allow_first_build_but_are_recorded_pending():
    a, r = ready(through_access_required=True, defer_passages=True)
    assert not missing_questions(a, r)
    p = Project(a, r)
    revision = p.generate()
    assert any(
        c.name == "Deferred cable opening" and c.result == "not_evaluated"
        for c in revision.checks
    )
    strict = r.model_copy(update={"defer_passages": False})
    assert any("through" in q for q in missing_questions(a, strict))
    with pytest.raises(ValueError, match="through"):
        compile_plan(a, strict)
    assert Project.new(a).requirements.defer_passages


def test_old_compilers_reject_new_openings_and_frame_changes_are_explicit():
    from fixture.planning import patch_requirements

    a, r = ready()
    r = r.model_copy(
        update={
            "fixture_openings": (
                FixtureOpening(
                    id="wire", body="stock-0", center=(0, 0, 0), axis="z", diameter=8
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="version 14"):
        compile_plan(a, r, compiler_version=13)
    with pytest.raises(ValueError, match="mounting frame"):
        patch_requirements(r, {"interface_id": "new-face"})


def test_multiple_openings_and_side_face_direction():
    import usd_brep as sm

    a, r = ready()
    p = Project(a, r)
    revision = p.generate()
    body = next(iter(revision.meshes))
    p.generate(opening_candidate(p, event_at(revision, body, (-10, 0, 0)), 6))
    second = p.generate(opening_candidate(p, event_at(p.current, body, (10, 0, 0)), 6))
    assert second.metrics["fixture_opening_count"] == 2
    assert not [c for c in second.checks if c.result == "failed"]

    q = Project(a, r)
    revision = q.generate()
    event = event_at(revision, body, (32, 0, -3))
    assert resolve_pick(revision, event)["axis"] == "x"
    side = q.generate(opening_candidate(q, event, 2))
    assert not [c for c in side.checks if c.result == "failed"]
    volumes = [
        sum(b.volume(relative_accuracy=1e-8) for b in sm.usd.import_breps(rev.artifact))
        for rev in (revision, side)
    ]
    assert volumes[0] - volumes[1] == pytest.approx(math.pi * 64, abs=0.01)


def test_separate_rib_obstruction_rejects_hole_and_keeps_current():
    a, r = sheet(sheet_construction="cut_weld")
    p = Project(a, r)
    initial = p.generate()
    rib = next(o for o in initial.plan.operations if o.body == "corner-rib-0")
    point = (rib.origin[0] + r.thickness / 2, -45, 0)
    event = event_at(initial, "mounting-platform", point)
    with pytest.raises(ValueError, match="blocks|edge|rim|Sheet"):
        p.generate(opening_candidate(p, event, 1))
    assert p.current.id == initial.id and p.requirements == r


def test_axis_aligned_mesh_chord_does_not_allow_native_curved_entry():
    import usd_brep as sm
    from fixture.contracts import Operation
    from fixture.custom_openings import check_cut

    body = sm.primitives.create_cylinder((0.0, 0.0, 0.0), 10.0, 6.0)
    tool = Operation(
        id="fixture-opening-wire",
        kind="relief",
        target="stock-0",
        shape="cylinder",
        axis="x",
        origin=(-11, 0, 3),
        size=(0.5, 0.5, 22),
        provenance={"position": "user"},
    )
    with pytest.raises(ValueError, match="flat|irregular"):
        check_cut(body, tool)
