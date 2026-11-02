import pytest

from fixture.contracts import FixtureOpening
from fixture.custom_openings import opening_candidate, remove_opening, resize_opening
from fixture.manufacturing import SHEET_METAL
from fixture.planning import (
    compile_plan,
    missing_questions,
    patch_requirements,
    proposals,
    proposal_requirements,
)
from fixture.project import Project, ROOT
from tests.test_custom_openings import event_at
from tests.test_geometry import ready


def bracket(fabrication="Machined stock"):
    a, r = ready(
        composition="l_bracket",
        mount_height=70,
        base_depth=40,
        fabrication=fabrication,
        thickness=3,
        surroundings="bolt",
        bench_fastener="M3",
        bench_hole_count=4,
    )
    p = Project(a, r)
    first = p.generate()
    p.generate(
        opening_candidate(p, event_at(first, "mounting-platform", (0, -45, 0)), 8)
    )
    return p


@pytest.mark.parametrize("fabrication", ["Machined stock", SHEET_METAL])
def test_bridge_transition_retains_size_requires_new_pick_and_reproduces(
    fabrication, tmp_path
):
    import cadquery as cq
    from fixture.step_export import prepare_step
    from scripts.reproduce import reproduce

    p = bracket(fabrication)
    previous, saved = p.current, p.requirements.fixture_openings[0]
    proposal = next(
        v for v in proposals(p.analysis, p.requirements) if v.id == "bridge"
    )
    candidate = proposal_requirements(p.requirements, proposal)
    pending = candidate.fixture_openings[0]
    assert pending.needs_placement and pending.id == saved.id
    assert pending.diameter == saved.diameter and pending.center == saved.center
    assert p.current is previous and not saved.needs_placement
    with pytest.raises(ValueError, match="version 15"):
        compile_plan(p.analysis, candidate, compiler_version=14)

    bridge = p.generate(candidate, "Switch fixture type")
    assert bridge.plan.version == 15
    assert bridge.metrics["fixture_opening_count"] == 0
    assert bridge.metrics["pending_fixture_opening_count"] == 1
    assert not [
        o for o in bridge.plan.operations if o.id.startswith("fixture-opening-")
    ]
    assert not [c for c in bridge.checks if c.result == "failed"]
    assert any(
        c.name == "Fixture openings awaiting placement" and c.result == "not_evaluated"
        for c in bridge.checks
    )
    archive = tmp_path / "pending.zip"
    archive.write_bytes(p.export(False))
    reproduce(archive, tmp_path / "reproduced")
    resumed = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert resumed.requirements.fixture_openings[0].needs_placement
    with pytest.raises(ValueError, match="Place this opening"):
        resize_opening(p, pending.id, 10)

    point = (0, -15, 0)
    picked = opening_candidate(
        p, event_at(bridge, "mounting-platform", point), saved.diameter, saved.id
    )
    assert (
        len(picked.fixture_openings) == 1
        and not picked.fixture_openings[0].needs_placement
    )
    assert picked.fixture_openings[0].id == saved.id
    after = p.generate(picked, "Reposition existing opening")
    assert after.metrics["fixture_opening_count"] == 1
    assert not after.metrics.get("pending_fixture_opening_count")
    shape = cq.importers.importStep(str(prepare_step(after))).val()
    tool = (
        cq.Workplane("XY")
        .center(0, -15)
        .circle(4)
        .extrude(200)
        .translate((0, 0, -100))
        .val()
    )
    assert shape.intersect(tool).Volume() < 0.01
    assert after.metrics["hole_count"] == previous.metrics["hole_count"] == 4
    assert after.metrics["base_hole_count"] == 4
    p.restore(previous.id)
    assert p.requirements.fixture_openings[0] == saved
    assert p.requirements.composition == "l_bracket"


def test_direct_type_change_is_guarded_and_same_type_revision_keeps_location():
    p = bracket()
    saved = p.requirements.fixture_openings[0]
    revision = p.generate(patch_requirements(p.requirements, {"reinforce": False}))
    assert revision.requirements.fixture_openings[0] == saved
    direct = p.requirements.model_copy(update={"composition": "bridge"})
    revision = p.generate(direct)
    assert revision.requirements.fixture_openings[0].needs_placement
    assert revision.metrics["fixture_opening_count"] == 0


def test_lock_failure_and_invalid_repick_keep_last_valid_revision():
    p = bracket()
    old, r = p.current, p.requirements
    p.requirements = r.model_copy(update={"locks": ("fixture_openings",)})
    with pytest.raises(ValueError, match="locked"):
        patch_requirements(p.requirements, {"composition": "bridge"})
    with pytest.raises(ValueError, match="locked"):
        p.generate(p.requirements.model_copy(update={"composition": "bridge"}))
    assert p.current is old and p.last_attempt.failure_kind == "design"
    p.requirements = r
    candidate = patch_requirements(r, {"composition": "bridge"})
    p.requirements = candidate
    with pytest.raises(ValueError, match="new fixture type"):
        opening_candidate(
            p,
            event_at(old, "mounting-platform", (0, -20, 0)),
            8,
            r.fixture_openings[0].id,
        )
    bridge = p.generate(candidate)
    pending = p.requirements
    # A valid mesh hit near the outer edge still fails the independent CAD rim check.
    wall = next(o for o in bridge.plan.operations if o.id == "mounting-platform")
    point = (wall.origin[0] + 0.1, -15, 0)
    invalid = opening_candidate(
        p, event_at(bridge, "mounting-platform", point), 8, r.fixture_openings[0].id
    )
    with pytest.raises(ValueError, match="edge|rim|irregular"):
        p.generate(invalid)
    assert p.current is bridge and p.requirements == pending


def test_multiple_pending_openings_retarget_to_new_bodies_independently():
    a, r = ready()
    p = Project(a, r)
    initial = p.generate()
    body = next(iter(initial.meshes))
    p.generate(opening_candidate(p, event_at(initial, body, (-10, 0, 0)), 6))
    p.generate(opening_candidate(p, event_at(p.current, body, (10, 0, 0)), 6))
    before = p.requirements.fixture_openings
    bridge = p.generate(patch_requirements(p.requirements, {"composition": "bridge"}))
    assert all(o.needs_placement for o in p.requirements.fixture_openings)
    assert bridge.metrics["pending_fixture_opening_count"] == 2
    candidate = opening_candidate(
        p, event_at(bridge, "mounting-platform", (-10, 0, 0)), 6, before[0].id
    )
    replaced = p.generate(candidate)
    assert replaced.metrics["pending_fixture_opening_count"] == 1
    assert replaced.metrics["fixture_opening_count"] == 1
    assert (
        next(o for o in p.requirements.fixture_openings if o.id == before[0].id).body
        == "mounting-platform"
    )
    final = p.generate(remove_opening(p, before[1].id))
    assert len(final.requirements.fixture_openings) == 1
    assert not final.metrics.get("pending_fixture_opening_count")


def test_pending_is_not_mistaken_for_required_through_access():
    a, r = ready(
        through_access_required=True,
        defer_passages=False,
        fixture_openings=(
            FixtureOpening(
                id="old", body="stock-0", center=(0, 0, 0), axis="z", diameter=8
            ),
        ),
    )
    candidate = patch_requirements(r, {"composition": "bridge"})
    assert candidate.defer_passages and not missing_questions(a, candidate)
    strict = candidate.model_copy(update={"defer_passages": False})
    assert any("through" in q for q in missing_questions(a, strict))
    with pytest.raises(ValueError, match="through"):
        compile_plan(a, strict)


def test_bounded_feedback_repair_preserves_pending_openings():
    from fixture.contracts import DesignReview, RepairChanges
    from fixture.workflow import generate_with_feedback

    p = bracket()
    candidate = p.requirements.model_copy(update={"composition": "bridge"})
    calls = []

    def review(context, messages, images):
        calls.append(context)
        assert context["attempt"]["requirements"]["fixture_openings"][0][
            "needs_placement"
        ]
        return DesignReview(
            verdict="revise" if len(calls) == 1 else "accept",
            summary="Review the platform margin.",
            findings=(),
            questions=(),
            changes=RepairChanges(margin=9) if len(calls) == 1 else RepairChanges(),
        )

    result = generate_with_feedback(p, review, "Test provider", candidate)
    assert len(calls) == 2 and result
    assert result.requirements.fixture_openings[0].needs_placement
    assert result.metrics["fixture_opening_count"] == 0
    assert result.metrics["pending_fixture_opening_count"] == 1
