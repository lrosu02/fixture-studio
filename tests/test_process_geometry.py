import pytest
import cadquery as cq
from fixture.contracts import Envelope, Plan, HardwareChoice
from fixture.project import Project
from fixture.step_export import prepare_step
from fixture.executor import execute
from fixture.validation import validate
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
