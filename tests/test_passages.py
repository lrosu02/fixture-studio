import io
import zipfile

import cadquery as cq
import pytest
import usd_brep as sm

from fixture.clearance import rear_regions, passage_options
from fixture.intake import analyze_file, selected_interface
from fixture.planning import (
    compile_plan,
    patch_requirements,
    proposals,
    proposal_requirements,
)
from fixture.project import Project
from fixture.executor import execute, primitive
from fixture.validation import validate
from fixture.step_export import prepare_step, _body
from tests.test_geometry import ready


def shallow_source(tmp_path):
    part = cq.importers.importStep("samples/synthetic_motor.step")
    part = part.union(cq.Workplane("XY").circle(3).extrude(-2))
    part = part.union(
        cq.Workplane("XY")
        .box(6, 6, 2, centered=(True, True, False))
        .translate((-24, -20, -2))
    )
    path = tmp_path / "shallow-protrusions.step"
    cq.exporters.export(part, str(path))
    a = analyze_file(path)
    interface = next(
        i
        for i in a.interfaces
        if abs(i.origin[2]) < 0.01 and i.z[2] > 0.9 and len(i.hole_ids) >= 4
    )
    holes = tuple(
        h for h, d in zip(interface.hole_ids, interface.diameters) if abs(d - 4) < 0.01
    )
    _, r = ready(
        composition="l_bracket", interface_id=interface.id, mounting_hole_ids=holes
    )
    profiles = rear_regions(a, selected_interface(a, r), r.rear_clearance)
    chosen = next(o.id for o in profiles if o.shape == "prism")
    return a, r, chosen


@pytest.mark.parametrize("composition", ["plate", "l_bracket", "bridge"])
def test_selected_blind_recess_becomes_through_and_survives_step(tmp_path, composition):
    a, r, chosen = shallow_source(tmp_path)
    r = r.model_copy(update={"composition": composition})
    p = Project(a, r)
    before = p.generate()
    updated = patch_requirements(r, {"rear_passages": (chosen,)})
    after = p.generate(updated, "Open the selected wire recess through")
    assert (
        after.parent == before.id
        and after.metrics["volume_mm3"] < before.metrics["volume_mm3"]
    )
    assert after.metrics["body_count"] == 1 and after.metrics["hole_count"] == 4
    assert [
        c.result for c in after.checks if c.name.startswith("Through passage:")
    ] == ["passed"]
    old_regions = {
        op.id: op for op in before.plan.operations if op.id.startswith("rear-relief")
    }
    passage = next(
        op for op in after.plan.operations if op.purpose.startswith("Through passage")
    )
    others = [
        op
        for op in after.plan.operations
        if op.id.startswith("rear-relief") and op.id != passage.id
    ]
    assert all(
        op.origin == old_regions[op.id].origin and op.size == old_regions[op.id].size
        for op in others
    )
    assert (
        passage.profile == old_regions[passage.id].profile
        and passage.origin[:2] == old_regions[passage.id].origin[:2]
    )
    step = prepare_step(after)
    shape = cq.importers.importStep(str(step)).val()
    # Independent full-depth Boolean test in the exported STEP domain.
    from fixture.cad_io import export_verified
    import re

    tool_path = tmp_path / "tool.usda"
    export_verified([primitive(passage)], tool_path)
    tools = [
        solid
        for block in re.split(r'\bdef BrepArray "[^"\n]+"', tool_path.read_text())[1:]
        for solid in _body(block)
    ]
    assert shape.intersect(cq.Compound.makeCompound(tools)).Volume() < 0.01
    before_bodies = sm.usd.import_breps(before.artifact)
    assert (
        sum(
            abs(sm.booleans.boolean_intersection(b, primitive(passage)).volume())
            for b in before_bodies
        )
        > 1
    )
    archive = tmp_path / "through.zip"
    archive.write_bytes(p.export())
    assert "fixture.step" in zipfile.ZipFile(io.BytesIO(p.export())).namelist()
    from scripts.reproduce import reproduce

    reproduce(archive, tmp_path / "rebuilt")


def test_blind_cut_fails_requested_through_check_and_depth_follows_thickness(tmp_path):
    a, r, chosen = shallow_source(tmp_path)
    selected = patch_requirements(r, {"rear_passages": (chosen,)})
    plan = compile_plan(a, selected)
    blind_plan = compile_plan(a, r)
    bodies, _, cuts = execute(blind_plan, a, tmp_path / "blind.usda")
    checks = validate(a, selected, blind_plan, bodies, cuts)
    assert (
        next(c for c in checks if c.name.startswith("Through passage:")).result
        == "failed"
    )
    for thickness in (4.0, 10.0):
        changed = patch_requirements(selected, {"thickness": thickness})
        deeper = compile_plan(a, changed)
        through = next(
            o for o in deeper.operations if o.purpose.startswith("Through passage")
        )
        assert (
            through.origin[2] < -thickness and through.origin[2] + through.size[2] > 0
        )
        bodies, _, cuts = execute(deeper, a, tmp_path / f"thickness-{thickness}.usda")
        assert not [
            c
            for c in validate(a, changed, deeper, bodies, cuts)
            if c.result == "failed"
        ]
    assert plan.parameters["rear_passage_count"] == 1


def test_passage_choices_locks_instances_and_legacy(tmp_path):
    a, r, chosen = shallow_source(tmp_path)
    assert all(c["blind_in_wall"] for c in passage_options(a, r))
    with pytest.raises(ValueError, match="unknown or duplicate"):
        compile_plan(a, r.model_copy(update={"rear_passages": ("missing",)}))
    with pytest.raises(ValueError, match="locked"):
        patch_requirements(
            r.model_copy(update={"locks": ("rear_passages",)}),
            {"rear_passages": (chosen,)},
        )
    selected = patch_requirements(r, {"rear_passages": (chosen,), "quantity": 2})
    plan = compile_plan(a, selected)
    assert plan.parameters["rear_passage_count"] == 2
    bodies, _, cuts = execute(plan, a, tmp_path / "two.usda")
    assert [
        c.result
        for c in validate(a, selected, plan, bodies, cuts)
        if c.name.startswith("Through passage:")
    ] == ["passed", "passed"]
    for version in (2, 3):
        legacy = compile_plan(a, r, compiler_version=version)
        assert legacy.version == version
        assert not any(
            o.purpose.startswith("Through passage") for o in legacy.operations
        )
    changed_face = patch_requirements(selected, {"interface_id": "another"})
    assert changed_face.rear_passages == ()


def test_ai_can_select_and_highlight_measured_rear_profile(tmp_path):
    from fixture.agent import Action, Changes, apply_action
    from fixture.viewer import assembly_figure

    a, r, chosen = shallow_source(tmp_path)
    action = Action(
        action="revise",
        changes=Changes(rear_passages=(chosen,)),
        questions=(),
        highlight_ids=(chosen,),
        explanation="Make the selected recess through.",
    )
    candidate = apply_action(a, r, action)
    assert candidate.rear_passages == (chosen,)
    revision = Project(a, candidate).generate()
    fig = assembly_figure(
        a, r.interface_id, revision, envelopes=False, highlight_ids=(chosen,)
    )
    assert len([t for t in fig.data if t.name == "Measured rear clearance"]) == 1
    with pytest.raises(ValueError, match="unknown feature"):
        apply_action(
            a, r, action.model_copy(update={"highlight_ids": ("rear-profile-999",)})
        )


def test_more_proposals_build_distinct_geometry_and_preserve_choices(tmp_path):
    a, r, chosen = shallow_source(tmp_path)
    r = r.model_copy(update={"rear_passages": (chosen,)})
    options = proposals(a, r)
    assert {p.title for p in options} >= {
        "L-bracket",
        "Open L-bracket",
        "Raised L-bracket",
        "Bridge support",
        "Raised bridge",
    }
    volumes = []
    for proposal in options:
        candidate = proposal_requirements(r, proposal)
        assert (
            candidate.mounting_hole_ids == r.mounting_hole_ids
            and candidate.rear_passages == r.rear_passages
        )
        plan = compile_plan(a, candidate)
        bodies, _, cuts = execute(plan, a, tmp_path / f"{proposal.id}.usda")
        assert not [
            c
            for c in validate(a, candidate, plan, bodies, cuts)
            if c.result == "failed"
        ]
        volumes.append(round(sum(b.volume() for b in bodies.values()), 1))
    assert len(set(volumes)) == len(options)
    locked = r.model_copy(
        update={"locks": ("composition", "reinforce", "mount_height")}
    )
    assert [p.id for p in proposals(a, locked)] == ["l_bracket"]
