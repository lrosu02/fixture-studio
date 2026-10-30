"""Regression: requested base holes must exist in native CAD and reopened STEP."""

import cadquery as cq
import pytest

from fixture.agent import Action, Changes
from fixture.base_mounting import BASE_HOLE_PURPOSE
from fixture.executor import execute
from fixture.planning import compile_plan, patch_requirements, missing_questions
from fixture.project import Project
from fixture.step_export import prepare_step
from fixture.validation import validate
from fixture.workflow import plan_design
from tests.test_geometry import ready
from tests.test_passages import shallow_source


@pytest.mark.parametrize(
    "kind,count",
    [
        ("l_bracket", 4),
        ("l_bracket", 3),
        ("l_bracket", 5),
        ("l_bracket", 1),
        ("l_bracket", 7),
        ("l_bracket", 20),
        ("bridge", 6),
        ("plate", 4),
        ("plate", 1),
        ("rails", 4),
    ],
)
def test_requested_base_holes_exist_and_old_defaults_reproduce(tmp_path, kind, count):
    a, r = ready(composition=kind, surroundings="bolt", bench_fastener="M3")
    legacy = compile_plan(a, r, compiler_version=4)
    r = patch_requirements(r, {"bench_hole_count": count})
    plan = compile_plan(a, r)
    bodies, _, cuts = execute(plan, a, tmp_path / "fixture.usda")
    assert len(cuts) == 4  # Source pattern is a separate relationship.
    base = [op for op in plan.operations if op.purpose == BASE_HOLE_PURPOSE]
    assert len(base) == count and len({op.origin for op in base}) == count
    assert not [c for c in validate(a, r, plan, bodies, cuts) if c.result == "failed"]
    if kind == "l_bracket" and count == 4:
        assert (
            len({op.origin[0] for op in base})
            == len({op.origin[2] for op in base})
            == 2
        )
    assert (
        compile_plan(
            a, r.model_copy(update={"bench_hole_count": None}), compiler_version=4
        )
        == legacy
    )
    with pytest.raises(ValueError, match="version 5"):
        compile_plan(a, r, compiler_version=4)
    with pytest.raises(ValueError, match="operation CAD budget"):
        compile_plan(a, patch_requirements(r, {"bench_hole_count": 1000000}))


def test_four_base_holes_and_wire_passage_survive_step_and_missing_holes_fail(tmp_path):
    a, r, chosen = shallow_source(tmp_path)
    r = patch_requirements(
        r,
        dict(
            surroundings="bolt",
            bench_fastener="M3",
            bench_hole_count=4,
            rear_passages=(chosen,),
            through_access_required=True,
        ),
    )
    p = Project(a, r)
    rev = p.generate()
    assert rev.metrics["hole_count"] == rev.metrics["base_hole_count"] == 4
    assert "4 part holes, 4 base holes" in rev.summary
    step = cq.importers.importStep(str(prepare_step(rev))).val()
    assert step.isValid() and len(step.Solids()) == 1
    base = [op for op in rev.plan.operations if op.purpose == BASE_HOLE_PURPOSE]
    foot = next(op for op in rev.plan.operations if op.id == "base-foot")
    for op in base:
        x, _, z = op.origin
        # Independent interior probe across the full foot, with solid material
        # beside it: a face dimple or missing stock cannot satisfy this check.
        probe = cq.Solid.makeCylinder(
            op.size[0] / 2 - 0.05,
            foot.size[1] + 2,
            cq.Vector(x, foot.origin[1] - 1, z),
            cq.Vector(0, 1, 0),
        )
        assert step.intersect(probe).Volume() < 0.01
        assert step.isInside(
            cq.Vector(x + op.size[0] / 2 + 0.5, foot.origin[1] + foot.size[1] / 2, z)
        )
    passage = next(
        op for op in rev.plan.operations if op.purpose.startswith("Through passage")
    )
    center = [
        passage.origin[k] + sum(v[k] for v in passage.profile) / len(passage.profile)
        for k in (0, 1)
    ]
    probe = cq.Solid.makeCylinder(
        0.2, passage.size[2], cq.Vector(*center, passage.origin[2]), cq.Vector(0, 0, 1)
    )
    assert step.intersect(probe).Volume() < 0.01
    two = compile_plan(a, r.model_copy(update={"bench_hole_count": 2}))
    bodies, _, cuts = execute(two, a, tmp_path / "only-two.usda")
    checks = validate(a, r, two, bodies, cuts)
    assert next(c for c in checks if c.name == "Base fastener count").result == "failed"
    checks = validate(a, r, rev.plan, bodies, cuts)
    assert (
        next(c for c in checks if c.name == "Base fastener geometry").result == "failed"
    )


def test_unresolved_passage_and_count_conflicts_keep_last_valid(tmp_path):
    a, r, chosen = shallow_source(tmp_path)
    p = Project(a, r)
    old = p.generate()
    action = Action(
        action="revise",
        changes=Changes(
            bench_hole_count=4,
            surroundings="bolt",
            bench_fastener="M3",
            through_access_required=True,
        ),
        questions=("Which recess needs the wire passage?",),
        highlight_ids=(),
        explanation="Four base holes and a through wire opening requested.",
    )
    assert not plan_design(
        p, lambda *args: action, "Four base holes and a through wire passage"
    )
    assert p.requirements.bench_hole_count == 4 and p.current == old
    assert any("through" in q for q in missing_questions(a, p.requirements))
    with pytest.raises(ValueError, match="through wire/tool"):
        p.generate()
    assert p.current == old
    resolved = patch_requirements(p.requirements, {"rear_passages": (chosen,)})
    p.generate(resolved)
    previous = p.current
    with pytest.raises(ValueError, match="base fasteners|Base holes do not fit"):
        p.generate(
            patch_requirements(resolved, {"base_depth": 13, "bench_hole_count": 12})
        )
    assert p.current == previous
    with pytest.raises(ValueError, match="locked"):
        patch_requirements(
            resolved.model_copy(update={"locks": ("bench_hole_count",)}),
            {"bench_hole_count": 2},
        )


def test_fifth_hole_is_centered_between_four_unchanged_corners_in_step(tmp_path):
    a, r = ready(
        composition="l_bracket",
        surroundings="bolt",
        bench_fastener="M3",
        bench_hole_count=5,
    )
    four = compile_plan(a, r.model_copy(update={"bench_hole_count": 4}))
    p = Project(a, r)
    revision = p.generate()
    corners = [op.origin for op in four.operations if op.purpose == BASE_HOLE_PURPOSE]
    base = [op for op in revision.plan.operations if op.purpose == BASE_HOLE_PURPOSE]
    assert len(base) == 5
    assert {op.origin for op in base[:4]} == set(corners)
    middle = tuple(sum(point[k] for point in corners) / 4 for k in range(3))
    assert base[-1].origin == pytest.approx(middle)
    assert (
        next(c for c in revision.checks if c.name == "Base pattern symmetry").result
        == "passed"
    )
    shape = cq.importers.importStep(str(prepare_step(revision))).val()
    foot = next(op for op in revision.plan.operations if op.id == "base-foot")
    for op in base:
        x, _, z = op.origin
        probe = cq.Solid.makeCylinder(
            op.size[0] / 2 - 0.05,
            foot.size[1] + 2,
            cq.Vector(x, foot.origin[1] - 1, z),
            cq.Vector(0, 1, 0),
        )
        assert shape.intersect(probe).Volume() < 0.01
        assert shape.isInside(
            cq.Vector(x + op.size[0] / 2 + 0.5, foot.origin[1] + foot.size[1] / 2, z)
        )
    assert shape.isValid() and len(shape.Solids()) == 1
    old = compile_plan(a, r, compiler_version=5)
    old_base = [op for op in old.operations if op.purpose == BASE_HOLE_PURPOSE]
    assert len({op.origin[0] for op in old_base}) == 2  # Legacy 3+2 stays reproducible.
    bodies, _, cuts = execute(old, a, tmp_path / "legacy.usda")
    assert not [c for c in validate(a, r, old, bodies, cuts) if c.result == "failed"]
    checks = validate(a, r, old.model_copy(update={"version": 6}), bodies, cuts)
    assert (
        next(c for c in checks if c.name == "Base pattern symmetry").result == "failed"
    )


def test_centered_hole_cannot_overlap_outer_bores():
    from fixture.base_mounting import two_lanes

    with pytest.raises(ValueError, match="Centered base hole does not fit"):
        two_lanes(-3, 3, -3, 3, 5, 3.4, center_odd=True)
