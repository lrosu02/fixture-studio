import pytest

from tests.test_geometry import ready
from fixture.manufacturing import SHEET_METAL
from fixture.planning import compile_plan
from fixture.executor import execute
from fixture.validation import validate


def sheet(**kw):
    return ready(
        **{
            "fabrication": SHEET_METAL,
            "thickness": 3,
            "composition": "l_bracket",
            "mount_height": 70,
            "base_depth": 40,
            "surroundings": "bolt",
            "bench_fastener": "M3",
            "bench_hole_count": 4,
            **kw,
        }
    )


@pytest.mark.parametrize(
    "composition,bodies_count,joints",
    [("plate", 1, 0), ("rails", 2, 0), ("l_bracket", 4, 5), ("bridge", 5, 4)],
)
def test_native_sheet_families(composition, bodies_count, joints, tmp_path):
    a, r = sheet(composition=composition)
    p = compile_plan(a, r)
    bodies, meshes, cuts = execute(p, a, tmp_path / "fixture.usda")
    checks = validate(a, r, p, bodies, cuts)
    assert not [c for c in checks if c.result == "failed"]
    assert len(bodies) == bodies_count == len(p.sheet_panels)
    assert len(p.sheet_joints) == joints
    assert len(cuts) == 4
    assert not any(o.kind in ("support", "fillet", "finish") for o in p.operations)
    assert (
        sum(o.purpose == "Surrounding attachment bolt clearance" for o in p.operations)
        == 4
    )


def test_limits_and_legacy():
    a, r = sheet()
    with pytest.raises(ValueError, match="compiler version 12"):
        compile_plan(a, r, compiler_version=11)
    with pytest.raises(ValueError, match="tab width/count"):
        compile_plan(a, r.model_copy(update={"sheet_tab_width": 200}))
    with pytest.raises(ValueError, match="0.5 to 12"):
        compile_plan(a, r.model_copy(update={"thickness": 13}))


@pytest.mark.parametrize(
    "style,gap,thickness", [("weld_only", 0.3, 2), ("tab_slot_weld", 0.2, 4)]
)
def test_sheet_revision_step_bundle_and_reproduction(style, gap, thickness, tmp_path):
    import io
    import json
    import zipfile
    import cadquery as cq
    from fixture.project import Project
    from fixture.step_export import prepare_step
    from scripts.reproduce import reproduce

    a, r = sheet(
        sheet_joint_style=style,
        sheet_root_gap=gap,
        thickness=thickness,
        sheet_tab_count=3,
        base_depth=50,
    )
    project = Project(a, r)
    first = project.generate()
    second = project.generate(
        r.model_copy(update={"thickness": thickness + 0.5}), "Change sheet thickness"
    )
    assert second.parent == first.id
    assert first.requirements.thickness == thickness
    assert first.plan.placements == second.plan.placements
    assert len(second.plan.sheet_panels) == 4
    assert sum(len(j.tabs) for j in second.plan.sheet_joints) == (
        9 if style == "tab_slot_weld" else 0
    )
    step = prepare_step(second)
    solids = cq.importers.importStep(str(step)).val().Solids()
    assert len(solids) == 4 and all(s.isValid() for s in solids)
    assert "FACETED_BREP" not in step.read_text()
    payload = project.export(False)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        record = json.loads(archive.read("sheet-metal.json"))
        assert record["root_gap_mm"] == gap
        assert len(record["panels"]) == 4 and len(record["joints"]) == 5
        assert archive.read("fixture.step") == step.read_bytes()
    archive = tmp_path / "sheet.zip"
    archive.write_bytes(payload)
    reproduce(archive, tmp_path / "reproduced")
    with pytest.raises(ValueError, match="tab width/count"):
        project.generate(
            second.requirements.model_copy(
                update={"sheet_joint_style": "tab_slot_weld", "sheet_tab_width": 300}
            )
        )
    assert project.current.id == second.id


def test_native_missing_slot_and_blind_pocket_detected(tmp_path):
    from fixture.contracts import Operation

    a, r = sheet()
    plan = compile_plan(a, r)
    first_slot = plan.sheet_joints[0].slots[0]
    modified = plan.model_copy(
        update={
            "operations": tuple(
                o.model_copy(update={"origin": (500, 500, 500)})
                if o.id == first_slot
                else o
                for o in plan.operations
            )
        }
    )
    bodies, _, cuts = execute(modified, a, tmp_path / "blocked-slot.usda")
    checks = validate(a, r, modified, bodies, cuts)
    assert any(c.name == "Sheet mating slots" and c.result == "failed" for c in checks)
    # A shallow pocket in a flat base is valid CAD, but invalid flat sheet cutting.
    foot = next(o for o in plan.operations if o.id == "base-foot")
    pocket = Operation(
        id="injected-blind-pocket",
        kind="relief",
        target="base-foot",
        origin=(-2, foot.origin[1] - 1, -25),
        size=(4, 2, 4),
        provenance={"source": "user"},
    )
    modified = plan.model_copy(update={"operations": (*plan.operations, pocket)})
    bodies, _, cuts = execute(modified, a, tmp_path / "blind.usda")
    checks = validate(a, r, modified, bodies, cuts)
    assert any(
        c.name == "Flat sheet thickness" and c.result == "failed" for c in checks
    )


def test_automatic_depth_and_ai_contract():
    from fixture.agent import Changes
    from fixture.planning import patch_requirements

    a, r = sheet(base_depth=None, sheet_tab_count=4)
    edits = Changes(sheet_slot_clearance=0.2, sheet_root_gap=0.1, sheet_tab_count=4)
    r = patch_requirements(r, edits.model_dump(exclude_none=True))
    p = compile_plan(a, r)
    assert p.parameters["base_depth_mm"] >= 30
    assert r.base_depth is None
    assert all(j.slot_clearance == 0.2 for j in p.sheet_joints)
    with pytest.raises(ValueError, match="locked"):
        patch_requirements(
            r.model_copy(update={"locks": ("sheet_tab_count",)}), {"sheet_tab_count": 3}
        )


def test_measured_rear_profiles_are_through_sheet(tmp_path):
    from tests.test_clearance import protruding_source
    from fixture.project import Project

    a, r, _ = protruding_source(tmp_path)
    r = r.model_copy(
        update={
            "fabrication": SHEET_METAL,
            "thickness": 3,
            "mount_height": 70,
            "base_depth": 40,
        }
    )
    rev = Project(a, r).generate()
    assert not r.rear_passages
    profiles = [o for o in rev.plan.operations if o.id.startswith("rear-relief-")]
    assert len(profiles) == 2
    assert all(o.origin[2] < -40 and o.origin[2] + o.size[2] > 0 for o in profiles)
    assert all(len(o.targets) == 4 for o in profiles)
    assert not [c for c in rev.checks if c.result == "failed"]


def test_other_part_and_six_instances(tmp_path):
    a, r = ready(
        "sensor_bracket.step",
        fabrication=SHEET_METAL,
        thickness=2,
        composition="bridge",
        mount_height=50,
        quantity=6,
        layout="grid",
        columns=3,
        clearance_diameter=4.5,
    )
    plan = compile_plan(a, r)
    bodies, _, cuts = execute(plan, a, tmp_path / "six-sensors.usda")
    assert len(cuts) == 18 and len(bodies) == 5
    assert not [c for c in validate(a, r, plan, bodies, cuts) if c.result == "failed"]


def test_sheet_rejects_secondary_machining_and_nonbolted_retention():
    from fixture.contracts import HardwareChoice

    a, r = sheet(part_hardware=HardwareChoice(style="countersink"))
    with pytest.raises(ValueError, match="plain through holes"):
        compile_plan(a, r)
    with pytest.raises(ValueError, match="Hole-free sheet retention"):
        compile_plan(a, r.model_copy(update={"part_attachment": "cradle"}))


def test_sheet_measured_base_can_expand_stock(tmp_path):
    from tests.test_existing_base import base_requirement
    from fixture.project import Project

    a, r = sheet(
        base_mount=base_requirement(),
        base_depth=None,
        base_offset_x=3,
        base_offset_y=-60,
        base_rotation=17,
    )
    revision = Project(a, r).generate()
    assert revision.metrics["base_hole_count"] == 4
    assert not [c for c in revision.checks if c.result == "failed"]
    assert (
        revision.plan.parameters["base_source_hash"]
        == r.base_mount.analysis.source_hash
    )
