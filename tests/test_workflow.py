from types import SimpleNamespace
import json
import zipfile
import io
import pytest
from fixture.contracts import Requirements, Envelope, Plan, Operation
from fixture.project import Project
from fixture.planning import patch_requirements, compile_plan, missing_questions
from fixture.agent import (
    Action,
    Changes,
    apply_action,
    offline_turn,
    plan_turn,
    strict_schema,
)
from fixture.executor import execute, primitive
from tests.test_geometry import ready, ROOT


def test_conversation_quantity_access_revision_and_restore():
    a, r = ready()
    p = Project.new(a)
    first = p.generate(r)
    action = offline_turn("quantity 6 grid 3 columns")
    updated = apply_action(a, p.requirements, action)
    second = p.generate(updated, "Six in a grid")
    assert len(second.plan.placements) == 6 and second.metrics["hole_count"] == 24
    updated = apply_action(
        a, p.requirements, offline_turn("more rear access with open supports")
    )
    third = p.generate(updated, "Open supports for rear access")
    assert third.plan.composition == "rails"
    assert third.metrics["volume_mm3"] < second.metrics["volume_mm3"]
    assert third.metrics["hole_count"] == 24
    p.restore(first.id)
    assert p.current.id == first.id and p.requirements.quantity == 1


def test_real_access_cut_and_export():
    a, r = ready()
    p = Project.new(a)
    first = p.generate(r)
    env = Envelope(
        id="rear-tool",
        minimum=(-4, -4, -8),
        maximum=(4, 4, 1),
        purpose="Finite rear tool access",
    )
    second = p.generate(
        patch_requirements(r, {"envelopes": (env,)}), "Add real opening"
    )
    assert first.metrics["volume_mm3"] - second.metrics["volume_mm3"] == pytest.approx(
        8 * 8 * 6, abs=0.02
    )
    check = next(c for c in second.checks if c.name == "Fixture access: rear-tool")
    assert check.result == "passed" and check.measured < 0.01
    payload = p.export()
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        assert "Brep" in z.read("fixture.usda").decode()
        assert json.loads(z.read("plan.json"))["source_hash"] == a.source_hash
        assert "requirements.json" in z.namelist()


def test_conflict_and_kernel_failure_preserve_last_valid(monkeypatch):
    a, r = ready(locks=("gap",))
    p = Project.new(a)
    first = p.generate(r)
    with pytest.raises(ValueError, match="locked"):
        apply_action(a, r, offline_turn("gap 2"))
    with pytest.raises(ValueError, match="width"):
        p.generate(patch_requirements(r, {"max_width": 20}))
    assert p.current.id == first.id

    def fail(*args, **kwargs):
        raise RuntimeError("Injected native modeling failure")

    monkeypatch.setattr("fixture.project.execute", fail)
    with pytest.raises(RuntimeError, match="Injected"):
        p.generate(r)
    assert p.current.id == first.id and p.analysis.source_hash == a.source_hash


def fake_client(result=None, error=None):
    def create(**kwargs):
        if error:
            raise error
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call", name="design_action", arguments=result
                )
            ]
        )

    return SimpleNamespace(responses=SimpleNamespace(create=create))


def test_model_contract_timeouts_and_missing_facts():
    a, r = ready()
    action = Action(
        action="revise",
        changes=Changes(quantity=2, layout="row"),
        questions=(),
        highlight_ids=(),
        explanation="Two stations",
    )
    received = plan_turn(
        a,
        r,
        [{"role": "user", "content": "hold 2"}],
        client=fake_client(action.model_dump_json()),
    )
    assert apply_action(a, r, received).quantity == 2
    with pytest.raises(ValueError):
        plan_turn(a, r, [], client=fake_client("{malformed"))
    with pytest.raises(TimeoutError):
        plan_turn(a, r, [], client=fake_client(error=TimeoutError("API timeout")))
    assert r.material is None and r.nominal_fastener is None
    incomplete = Requirements(purpose="continuous running", quantity=6)
    questions = missing_questions(a, incomplete)
    assert len(questions) > 3
    assert any("manufacturing method" in q for q in questions)
    assert any("concept assumptions" in q for q in questions)
    incomplete = incomplete.model_copy(
        update=dict(
            interface_id=r.interface_id, mounting_confirmed=True, clearance_diameter=3.5
        )
    )
    assert any("move or rotate" in q for q in missing_questions(a, incomplete))
    schema = strict_schema(Action.model_json_schema())
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False


def test_reject_bad_plans_before_native_work():
    a, r = ready()
    p = compile_plan(a, r)
    d = p.model_dump()
    d["operations"][1]["kind"] = "execute_python"
    with pytest.raises(ValueError):
        Plan.model_validate(d)
    d = p.model_dump()
    d["operations"][1]["depends_on"] = ["missing"]
    with pytest.raises(ValueError):
        Plan.model_validate(d)
    d = p.model_dump()
    d["operations"][1]["size"] = [-1, 2, 3]
    with pytest.raises(ValueError):
        Plan.model_validate(d)
    d = p.model_dump()
    d["operations"][2]["hole_ids"] = ["invented"]
    with pytest.raises(ValueError, match="references"):
        execute(Plan.model_validate(d), a, ROOT / "artifacts" / "bad.usda")


def test_primitive_vocabulary_and_contact_conflict():
    for shape, size in [
        ("box", (20, 10, 4)),
        ("cylinder", (10, 10, 4)),
        ("slot", (20, 6, 4)),
    ]:
        b = primitive(
            Operation(
                id="primitive",
                kind="stock",
                shape=shape,
                size=size,
                body="a",
                provenance={"size": "user"},
            )
        )
        assert b.is_manifold_solid() and b.volume() > 0
    a, r = ready()
    env = Envelope(
        id="bad",
        minimum=(-30, -20, -8),
        maximum=(30, 20, 1),
        purpose="Conflicting access",
    )
    with pytest.raises(ValueError, match="contact"):
        compile_plan(a, r.model_copy(update={"envelopes": (env,)}))


def test_selected_measured_holes():
    a, r = ready()
    i = next(i for i in a.interfaces if i.id == r.interface_id)
    r = r.model_copy(update={"mounting_hole_ids": i.hole_ids[:2]})
    rev = Project.new(a).generate(r)
    assert rev.metrics["hole_count"] == 2


def test_connected_support_combine_and_persistent_restore():
    a, r = ready()
    plan = Plan(
        source_hash=a.source_hash,
        interface_id=r.interface_id,
        composition="plate",
        placements=((0, 0, 0),),
        parameters={},
        operations=(
            Operation(
                id="stock",
                kind="stock",
                body="base",
                size=(10, 10, 4),
                provenance={"size": "user"},
            ),
            Operation(
                id="support",
                kind="support",
                body="support",
                target="base",
                origin=(0, 0, 4),
                size=(5, 5, 4),
                depends_on=("stock",),
                provenance={"size": "user"},
            ),
            Operation(
                id="join",
                kind="combine",
                target="base",
                other="support",
                depends_on=("support",),
                provenance={"mode": "user"},
            ),
        ),
    )
    bodies, _, _ = execute(plan, a, ROOT / "artifacts" / "support-union.usda")
    assert len(bodies) == 1 and bodies["base"].volume() == pytest.approx(500)
    p = Project.new(a)
    rev = p.generate(r)
    loaded = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert loaded.current.id == rev.id and loaded.analysis.source_hash == a.source_hash
