import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image
from fixture.agent import Action, Changes, review_turn
from fixture.contracts import DesignReview, RepairChanges, Check
from fixture.project import Project
from fixture.subscription import subscription_review
from fixture.workflow import plan_design, generate_with_feedback
from tests.test_geometry import ready, ROOT


def decision(verdict="accept", **changes):
    return DesignReview(
        verdict=verdict,
        summary="Geometric concept reviewed; operating performance remains unassessed.",
        findings=("Measured mounting pattern retained.",),
        changes=RepairChanges(**changes),
        questions=(),
    )


@pytest.mark.parametrize(
    "specimen,diameter,holes",
    [
        ("synthetic_motor.step", 3.5, 4),
        ("sensor_bracket.step", 4.5, 3),
    ],
)
def test_native_generation_review_views_and_export(specimen, diameter, holes):
    a, r = ready(specimen, clearance_diameter=diameter)
    p = Project(a, r)
    calls = []

    def review(context, messages, images):
        calls.append(context)
        assert context["attempt"]["metrics"]["hole_count"] == holes
        assert not context["attempt"]["error"]
        assert any(c["result"] == "not_evaluated" for c in context["attempt"]["checks"])
        assert len(images) == 1
        with Image.open(images[0]) as image:
            assert image.size == (1200, 430)
            assert len(image.convert("RGB").getcolors(1000000)) > 100
        return decision()

    first = generate_with_feedback(p, review, "Test double")
    assert len(calls) == 1 and len(p.revisions) == 1
    assert p.feedback[-1].outcome == "accepted"
    assert p.feedback[-1].build.revision_id == first.id
    restored = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert restored.feedback == p.feedback
    second = p.generate(r)
    with zipfile.ZipFile(io.BytesIO(p.export())) as z:
        assert json.loads(z.read("ai-feedback.json")) == []
    p.restore(first.id)
    with zipfile.ZipFile(io.BytesIO(p.export())) as z:
        feedback = json.loads(z.read("ai-feedback.json"))
        assert len(feedback) == 1 and feedback[0]["build"]["revision_id"] != second.id


def test_failed_plan_gets_one_supported_repair_then_real_cad():
    a, r = ready(max_width=63, locks=("max_width",))
    p = Project(a, r)
    calls = []

    def review(context, messages, images):
        calls.append(context)
        if len(calls) == 1:
            assert "exceeds max_width" in context["attempt"]["error"]
            assert not images and context["attempt"]["revision_id"] is None
            return decision("revise", margin=7)
        assert context["automatic_repair"]["remaining"] == 0
        assert not context["attempt"]["error"] and images
        return decision()

    result = generate_with_feedback(p, review, "Test double")
    assert len(calls) == 2 and len(p.revisions) == 1
    assert result.plan.parameters["width_mm"] == pytest.approx(62)
    assert p.requirements.max_width == 63 and p.requirements.margin == 7
    assert [f.outcome for f in p.feedback] == ["repair", "accepted"]


@pytest.mark.parametrize(
    "restrictions", [dict(locks=("margin",)), dict(provenance={"margin": "user"})]
)
def test_review_cannot_change_locks_or_user_dimensions(restrictions):
    a, r = ready(**restrictions)
    p = Project(a, r)
    generate_with_feedback(p, lambda *args: decision("revise", margin=9), "Test double")
    assert len(p.revisions) == 1 and p.requirements.margin == 8
    assert p.feedback[-1].outcome == "repair_blocked"


def test_repair_limit_and_review_error_preserve_valid_geometry():
    a, r = ready()
    p = Project(a, r)

    def review(context, *args):
        return decision(
            "revise", margin=context["attempt"]["requirements"]["margin"] + 1
        )

    generate_with_feedback(p, review, "Test double")
    assert len(p.revisions) == 2 and p.requirements.margin == 9
    assert p.feedback[-1].outcome == "repair_limit"

    def timeout(*args):
        raise TimeoutError("Injected review timeout")

    result = generate_with_feedback(p, timeout, "Test double")
    assert result and p.feedback[-1].outcome == "review_error"
    assert "timeout" in p.feedback[-1].note
    assert p.current.id == result.id


def test_failed_validation_is_sent_to_reviewer_and_cannot_be_accepted(monkeypatch):
    a, r = ready()
    p = Project(a, r)
    previous = p.generate()
    failed = Check(
        name="Injected topology failure",
        method="Test double",
        measured="invalid",
        result="failed",
        correction="Review stock",
    )
    monkeypatch.setattr("fixture.project.validate", lambda *args: (failed,))

    def review(context, messages, images):
        assert context["attempt"]["checks"][0]["result"] == "failed"
        assert context["attempt"]["error"] and not images
        return decision()

    generate_with_feedback(p, review, "Test double")
    assert p.current.id == previous.id and len(p.revisions) == 1
    assert p.feedback[-1].outcome == "review_error"
    assert "verdict was rejected" in p.feedback[-1].note


def test_start_prepares_proposal_and_preserves_explicit_dimensions():
    a, r = ready()
    p = Project(a, r)
    action = Action(
        action="build",
        changes=Changes(quantity=2, margin=10),
        questions=(),
        highlight_ids=(),
        explanation="Two parts on a common plate.",
    )
    assert not plan_design(
        p, lambda *args: action, "Hold two of these with 10 mm margin", start=True
    )
    assert not p.revisions and p.requirements.quantity == 2
    assert p.requirements.provenance["margin"] == "user"
    assert p.messages[0]["content"] == "Hold two of these with 10 mm margin"
    unsupported = action.model_copy(update={"action": "unsupported"})
    before = p.requirements
    assert not plan_design(p, lambda *args: unsupported, "A conformal nest")
    assert p.requirements == before and p.stage == "clarifying"
    p = Project.new(a)
    assert not plan_design(p, lambda *args: action, "Generate")
    assert not p.requirements.mounting_confirmed and not p.revisions
    assert "Before generating" in p.messages[-1]["content"]


def test_review_adapters_send_images_and_reject_arbitrary_changes(
    tmp_path, monkeypatch
):
    image = tmp_path / "review.png"
    Image.new("RGB", (20, 20)).save(image)
    result = decision()

    def create(**kwargs):
        assert kwargs["tool_choice"]["name"] == "design_review"
        assert kwargs["store"] is False
        assert kwargs["input"][0]["content"][1]["image_url"].startswith(
            "data:image/png;base64,"
        )
        return SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    name="design_review",
                    arguments=result.model_dump_json(),
                )
            ]
        )

    assert (
        review_turn(
            {},
            [],
            (image,),
            client=SimpleNamespace(responses=SimpleNamespace(create=create)),
        )
        == result
    )
    monkeypatch.setenv("FIXTURE_CODEX_PATH", "codex.exe")
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret-not-real")

    def runner(command, **kwargs):
        assert "OPENAI_API_KEY" not in kwargs["env"]
        if command[1:] == ["login", "status"]:
            return SimpleNamespace(
                returncode=0, stdout="Logged in using ChatGPT", stderr=""
            )
        assert command[command.index("--image") + 1] == str(image.resolve())
        assert "features.shell_tool=false" in command
        schema = json.loads(
            Path(command[command.index("--output-schema") + 1]).read_text()
        )
        assert "verdict" in schema["properties"]
        Path(command[command.index("--output-last-message") + 1]).write_text(
            result.model_dump_json()
        )
        return SimpleNamespace(returncode=0)

    assert subscription_review({}, [], (image,), runner=runner) == result
    bad = result.model_dump()
    bad["changes"] = {"interface_id": "invented", "clearance_diameter": 100}
    with pytest.raises(ValueError):
        DesignReview.model_validate(bad)
