import io
import json
import zipfile
import pytest
from streamlit.testing.v1 import AppTest
from fixture.agent import (
    Action,
    Changes,
    apply_action,
    planner_context,
    requests_geometry,
)
from fixture.contracts import PrintSettings, Requirements
from fixture.manufacturing import FDM, save_manufacturing
from fixture.planning import missing_questions
from fixture.project import Project
from tests.test_geometry import ROOT, ready


def test_method_persists_in_revisions_and_legacy_records_still_load():
    a, r = ready()
    p = Project(a, r)
    save_manufacturing(p, FDM)
    assert p.requirements.provenance["fabrication"] == "user"
    assert not missing_questions(a, p.requirements)
    first = p.generate()
    save_manufacturing(p, "Machined stock")
    with zipfile.ZipFile(io.BytesIO(p.export())) as z:
        record = json.loads(z.read("manufacturing.json"))
        assert record["fabrication"] == FDM
        assert "print_settings" not in record and "material" not in record
        assert "single printed part" in record["design_guidance"]
    second = p.generate()
    assert first.plan != second.plan
    assert first.plan.parameters["manufacturing_geometry"].startswith("45 degree")
    assert second.plan.parameters["manufacturing_geometry"].startswith("Rounded")
    p.restore(first.id)
    restored = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert restored.requirements.fabrication == FDM
    old = Requirements.model_validate(
        {
            **r.model_dump(),
            "material": "PETG",
            "print_settings": PrintSettings(
                layer_height_mm=0.2, wall_count=4
            ).model_dump(),
        }
    )
    assert old.print_settings.wall_count == 4
    context = planner_context(a, old)["requirements"]
    assert "print_settings" not in context and "material" not in context
    assert (
        Requirements.model_validate(
            r.model_dump(exclude={"print_settings"})
        ).print_settings
        == PrintSettings()
    )


def test_manufacturing_conversation_changes_method_without_building():
    a, r = ready()
    action = Action(
        action="revise",
        changes=Changes(fabrication=FDM),
        questions=(),
        highlight_ids=(),
        explanation="Use a printing concept.",
    )
    result = apply_action(a, r, action)
    assert result.fabrication == FDM
    assert not requests_geometry(action)
    assert requests_geometry(action.model_copy(update={"action": "build"}))
    locked = r.model_copy(update={"locks": ("fabrication",)})
    with pytest.raises(ValueError, match="locked"):
        apply_action(a, locked, action)
    p = Project(a, locked)
    with pytest.raises(ValueError, match="locked"):
        save_manufacturing(p, FDM)
    assert p.requirements == locked
    with pytest.raises(ValueError):
        Changes.model_validate({"print_settings": {"infill_percent": 35}})


def test_manufacturing_ui_only_asks_method(monkeypatch):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()

    def control(kind, label):
        return next(x for x in getattr(app, kind) if x.label == label)

    control("button", "Load example").click().run()
    original = app.session_state["project"].requirements
    control("selectbox", "Manufacturing method").select(FDM).run()
    assert app.session_state["project"].requirements == original
    labels = [
        x.label
        for kind in ("text_input", "number_input", "selectbox", "text_area")
        for x in getattr(app, kind)
    ]
    assert not any(
        any(
            word in label.lower()
            for word in (
                "filament",
                "printing material",
                "infill",
                "nozzle",
                "layer height",
                "printer /",
            )
        )
        for label in labels
    )
    control("button", "Save manufacturing").click().run()
    assert not app.exception
    assert app.session_state["project"].requirements.fabrication == FDM
    assert any("single printed part" in x.value for x in app.caption)
    monkeypatch.setattr(
        "fixture.subscription.subscription_turn",
        lambda *args: Action(
            action="revise",
            changes=Changes(fabrication="Machined stock"),
            questions=(),
            highlight_ids=(),
            explanation="Use machining.",
        ),
    )
    control("selectbox", "Conversation mode").select(
        "ChatGPT subscription (Codex CLI)"
    ).run()
    app.chat_input[0].set_value(
        "Change the manufacturing method to machining, do not build."
    ).run()
    assert app.session_state["project"].requirements.fabrication == "Machined stock"
    assert app.session_state["project"].current is None
    assert app.session_state["project"].error is None
    control("selectbox", "Manufacturing method").select("Other / custom").run()
    control("text_input", "Custom manufacturing method").set_value(
        "Waterjet stock"
    ).run()
    control("button", "Save manufacturing").click().run()
    assert app.session_state["project"].requirements.fabrication == "Waterjet stock"
