import pytest
import cadquery as cq
from fixture.contracts import HardwareChoice, Plan
from fixture.project import Project
from fixture.step_export import prepare_step
from fixture.executor import execute
from fixture.validation import validate
from tests.test_geometry import ready


@pytest.mark.parametrize("style", ["counterbore", "countersink", "nut_pocket"])
@pytest.mark.parametrize("composition", ["plate", "l_bracket"])
def test_hardware_native_and_step(style, composition):
    choice = HardwareChoice(style=style, driver_diameter=7)
    a, r = ready(
        composition=composition,
        surroundings="bolt",
        nominal_fastener="M3",
        clearance_diameter=None,
        bench_fastener="M3",
        margin=16,
        part_hardware=choice,
        base_hardware=choice,
    )
    p = Project(a, r)
    rev = p.generate()
    step = prepare_step(rev)
    solids = cq.importers.importStep(str(step)).val().Solids()
    assert len(solids) == 1 and all(s.isValid() for s in solids)
    assert all(c.result != "failed" for c in rev.checks)
    assert rev.plan.parameters["hardware_seats"] == 6
    if style == "countersink":
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cone

        assert (
            sum(
                BRepAdaptor_Surface(f.wrapped).GetType() == GeomAbs_Cone
                for f in solids[0].Faces()
            )
            == 6
        )


def test_hardware_missing_cut_rejected_and_invalid_revision_preserved(tmp_path):
    a, r = ready(
        nominal_fastener="M3", part_hardware=HardwareChoice(style="counterbore")
    )
    p = Project(a, r)
    rev = p.generate()
    ops = []
    for op in rev.plan.operations:
        if op.id.startswith("hardware-"):
            continue
        ops.append(op.model_copy(update={"depends_on": (ops[-1].id,) if ops else ()}))
    plan = Plan.model_validate({**rev.plan.model_dump(), "operations": ops})
    bodies, _, cuts = execute(plan, a, tmp_path / "missing.usda")
    assert any(
        c.name.startswith("Hardware clearance") and c.result == "failed"
        for c in validate(a, r, plan, bodies, cuts)
    )
    with pytest.raises(ValueError, match="1 mm"):
        p.generate(r.model_copy(update={"thickness": 3}))
    assert p.current.id == rev.id


def test_custom_hardware_and_locks():
    from fixture.planning import patch_requirements, compile_plan

    a, r = ready(
        nominal_fastener="#4", part_hardware=HardwareChoice(style="counterbore")
    )
    with pytest.raises(ValueError, match="explicit"):
        compile_plan(a, r)
    r = patch_requirements(
        r,
        {"part_hardware": HardwareChoice(style="counterbore", diameter=5.8, depth=2.8)},
    )
    assert Project(a, r).generate()
    with pytest.raises(ValueError, match="locked"):
        patch_requirements(
            r.model_copy(update={"locks": ("part_hardware",)}),
            {"part_hardware": HardwareChoice()},
        )
    locked = r.model_copy(update={"locks": ("part_hardware",)})
    assert (
        patch_requirements(
            locked, {"part_hardware": r.part_hardware.model_dump()}
        ).part_hardware
        == r.part_hardware
    )
