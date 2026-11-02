import pytest
import cadquery as cq
from fixture.contracts import Envelope, Plan, HardwareChoice
from fixture.project import Project
from fixture.step_export import prepare_step
from fixture.executor import execute
from fixture.validation import validate
from fixture.planning import compile_plan
from tests.test_geometry import ready


@pytest.mark.parametrize("fabrication", ["3D printing", "Machined stock"])
@pytest.mark.parametrize("composition", ["plate", "rails", "l_bracket", "bridge"])
def test_process_geometry_and_step(fabrication, composition):
    a, r = ready(
        composition=composition,
        fabrication=fabrication,
        manufacturing_features=True,
        surroundings="bolt",
        bench_fastener="M3",
        nominal_fastener="M3",
        clearance_diameter=None,
        margin=16,
    )
    p = Project(a, r)
    rev = p.generate()
    step = prepare_step(rev)
    assert cq.importers.importStep(str(step)).val().isValid()
    assert rev.plan.parameters["process_radius_mm"] == 2
    assert any(
        c.name.startswith("Manufacturing corners") and c.result == "passed"
        for c in rev.checks
    )
    assert (
        rev.metrics["volume_mm3"]
        < Project(a, r.model_copy(update={"manufacturing_features": False}))
        .generate()
        .metrics["volume_mm3"]
    )


def test_machined_access_corner_relief_and_native_fault(tmp_path):
    a, r = ready(
        manufacturing_features=True,
        envelopes=(
            Envelope(
                id="cable",
                minimum=(-3, -3, -7),
                maximum=(3, 3, 1),
                purpose="through cable opening",
            ),
        ),
    )
    p = Project(a, r)
    rev = p.generate()
    assert sum(o.id.startswith("process-corner") for o in rev.plan.operations) == 4
    ops = []
    for o in rev.plan.operations:
        if o.id.startswith("process-corner"):
            continue
        ops.append(o.model_copy(update={"depends_on": (ops[-1].id,) if ops else ()}))
    plan = Plan.model_validate({**rev.plan.model_dump(), "operations": ops})
    bodies, _, cuts = execute(plan, a, tmp_path / "uncut.usda")
    assert any(
        c.name.startswith("Cutter clearance") and c.result == "failed"
        for c in validate(a, r, plan, bodies, cuts)
    )


def test_hardware_and_process_combination_and_legacy_default():
    a, r = ready(
        composition="l_bracket",
        manufacturing_features=True,
        fabrication="3D printing",
        part_hardware=HardwareChoice(style="countersink"),
        nominal_fastener="M3",
        clearance_diameter=None,
        surroundings="bolt",
        bench_fastener="M3",
        base_hardware=HardwareChoice(style="counterbore"),
        margin=16,
    )
    rev = Project(a, r).generate()
    assert prepare_step(rev)
    legacy = r.model_dump(exclude={"manufacturing_features", "process_radius"})
    from fixture.contracts import Requirements

    assert Requirements.model_validate(legacy).manufacturing_features is False


@pytest.mark.parametrize("fabrication", ["3D printing", "Machined stock"])
def test_joined_corner_finish_removes_wall_ledge_and_detects_missing_finish(
    tmp_path, fabrication
):
    import usd_brep as sm
    from fixture.executor import primitive
    from fixture.process_geometry import joined_corner_finish

    a, r = ready(
        composition="l_bracket", fabrication=fabrication, manufacturing_features=True
    )
    plan = compile_plan(a, r)
    legacy = compile_plan(a, r, compiler_version=10)
    assert not any(o.kind == "finish" for o in legacy.operations)
    old, _, _ = execute(legacy, a, tmp_path / "legacy.usda")
    finish = joined_corner_finish(r, plan)
    square = finish.model_copy(update={"shape": "box", "corner_radius": None})
    removed = sm.booleans.boolean_difference(primitive(square), primitive(finish))
    ledge = abs(
        sm.booleans.boolean_intersection(
            old[finish.target].copy(), removed.copy()
        ).volume()
    )
    assert ledge > 1  # Real wall/rib material overhangs the old finished base corners.

    rev = Project(a, r).generate()
    current, _, _ = execute(rev.plan, a, tmp_path / "current.usda")
    assert (
        abs(
            sm.booleans.boolean_intersection(
                current[finish.target].copy(), removed.copy()
            ).volume()
        )
        < 0.01
    )
    assert any(
        c.name == "Joined exterior corners" and c.result == "passed" for c in rev.checks
    )
    assert cq.importers.importStep(str(prepare_step(rev))).val().isValid()
    assert (
        sum(o.kind == "mount" for o in plan.operations)
        == sum(o.kind == "mount" for o in legacy.operations)
        > 0
    )

    missing = plan.model_copy(
        update={"operations": tuple(o for o in plan.operations if o.kind != "finish")}
    )
    defective, _, cuts = execute(missing, a, tmp_path / "missing-finish.usda")
    assert any(
        c.name == "Joined exterior corners" and c.result == "failed"
        for c in validate(a, r, missing, defective, cuts)
    )
