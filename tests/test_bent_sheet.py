import pytest

from tests.test_sheet_metal import sheet
from fixture.planning import compile_plan
from fixture.project import Project
from fixture.step_export import prepare_step


@pytest.mark.parametrize(
    "thickness,radius,gap,reinforce",
    [(3, None, 0, True), (2, 4, 0.2, True), (4, 5, 0, False)],
)
def test_bent_l_sheet_native_and_step(thickness, radius, gap, reinforce):
    import cadquery as cq
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    a, r = sheet(
        sheet_construction="bent_weld",
        thickness=thickness,
        sheet_bend_radius=radius,
        sheet_root_gap=gap,
        reinforce=reinforce,
        base_depth=50,
    )
    revision = Project(a, r).generate()
    assert revision.metrics["body_count"] == (3 if reinforce else 1)
    assert revision.metrics["base_hole_count"] == 4
    assert len(revision.plan.sheet_bends) == 1
    assert not [c for c in revision.checks if c.result == "failed"]
    solids = cq.importers.importStep(str(prepare_step(revision))).val().Solids()
    assert len(solids) == (3 if reinforce else 1) and all(s.isValid() for s in solids)
    radii = [
        BRepAdaptor_Surface(f.wrapped).Cylinder().Radius()
        for s in solids
        for f in s.Faces()
        if BRepAdaptor_Surface(f.wrapped).GetType() == GeomAbs_Cylinder
    ]
    assert any(x == pytest.approx(radius or thickness) for x in radii)
    assert any(x == pytest.approx((radius or thickness) + thickness) for x in radii)


def test_bent_limits_and_historical_sheet():
    a, r = sheet(sheet_construction="bent_weld")
    with pytest.raises(ValueError, match="version 13"):
        compile_plan(a, r, compiler_version=12)
    with pytest.raises(ValueError, match="supports L-brackets"):
        compile_plan(a, r.model_copy(update={"composition": "bridge"}))
    with pytest.raises(ValueError, match="insufficient straight flange"):
        compile_plan(a, r.model_copy(update={"sheet_bend_radius": 90}))
    assert (
        compile_plan(
            a,
            r.model_copy(update={"sheet_construction": "cut_weld"}),
            compiler_version=12,
        ).version
        == 12
    )


def test_bend_revision_reproduction_and_detected_obstruction(tmp_path):
    from fixture.executor import execute
    from fixture.validation import validate
    from scripts.reproduce import reproduce

    a, r = sheet(sheet_construction="bent_weld", base_depth=50)
    p = Project(a, r)
    initial = p.generate()
    revision = p.generate(
        r.model_copy(update={"thickness": 4, "sheet_bend_radius": 5}),
        "Change gauge and bend radius",
    )
    assert (
        revision.parent == initial.id
        and revision.plan.placements == initial.plan.placements
    )
    assert revision.plan.parameters["outside_bend_radius_mm"] == 9
    archive = tmp_path / "bent.zip"
    archive.write_bytes(p.export(False))
    reproduce(archive, tmp_path / "rebuilt")
    # Fill the curved corner while preserving a valid solid and recorded bend.
    operations = tuple(
        o.model_copy(update={"shape": "box", "bend_radius": None})
        if o.id == "wall-base-bend"
        else o
        for o in revision.plan.operations
    )
    corrupted = revision.plan.model_copy(update={"operations": operations})
    bodies, _, cuts = execute(corrupted, a, tmp_path / "square-corner.usda")
    assert any(
        c.name.startswith("Continuous sheet bend") and c.result == "failed"
        for c in validate(a, revision.requirements, corrupted, bodies, cuts)
    )
    with pytest.raises(ValueError):
        p.generate(revision.requirements.model_copy(update={"sheet_bend_radius": 90}))
    assert p.current.id == revision.id


def test_bent_measured_rear_clearances_stay_through(tmp_path):
    from tests.test_clearance import protruding_source
    from fixture.manufacturing import SHEET_METAL

    a, r, _ = protruding_source(tmp_path)
    r = r.model_copy(
        update={
            "fabrication": SHEET_METAL,
            "sheet_construction": "bent_weld",
            "thickness": 3,
            "base_depth": 50,
            "mount_height": 70,
        }
    )
    revision = Project(a, r).generate()
    assert not [c for c in revision.checks if c.result == "failed"]
    assert revision.plan.parameters["rear_passage_count"] == 2
    assert (
        len([c for c in revision.checks if c.name.startswith("Through passage")]) == 2
    )
