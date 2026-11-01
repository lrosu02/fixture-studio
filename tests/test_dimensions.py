from pathlib import Path
from types import SimpleNamespace
import pytest
from fixture.dimensions import dimension_figure, edit_dimension, select_dimension
from fixture.project import Project
from tests.test_geometry import ready


def test_dimension_edit_rebuild_preserves_measurements_and_locks():
    a, r = ready()
    p = Project(a, r)
    first = p.generate()
    fig = dimension_figure(a, first)
    assert any(
        a.xref == "paper" and "thickness" in a.text.lower() for a in fig.layout.annotations
    )
    assert not any(t.meta and t.meta.get("dimension") for t in fig.data)
    changed = p.generate(edit_dimension(r, "thickness", 8), "Thicker stock")
    assert (
        changed.parent == first.id
        and changed.metrics["volume_mm3"] > first.metrics["volume_mm3"]
    )
    assert changed.plan.interface_id == first.plan.interface_id
    with pytest.raises(ValueError, match="locked"):
        edit_dimension(r.model_copy(update={"locks": ("thickness",)}), "thickness", 9)
    with pytest.raises(ValueError, match="old"):
        select_dimension(r, dict(context="old", field="thickness"), "current")
    with pytest.raises(ValueError):
        edit_dimension(r, "thickness", -1)
    with pytest.raises(ValueError):
        edit_dimension(r, "mounting_hole_ids", 8)


def test_on_model_ui_rebuild(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(
        "fixture.dimensions.component",
        lambda: lambda **kw: SimpleNamespace(picked=None),
    )
    a, r = ready()
    p = Project(a, r)
    first = p.generate()
    ui = AppTest.from_file(str(Path("app.py").resolve()), default_timeout=45)
    ui.session_state["project"] = p
    ui.run()
    next(s for s in ui.selectbox if s.label == "Conversation mode").select(
        "Offline commands"
    ).run()
    next(c for c in ui.checkbox if c.label == "Edit fixture dimensions").check().run()
    next(s for s in ui.selectbox if s.label == "Dimension to edit").select(
        "thickness"
    ).run()
    next(n for n in ui.number_input if n.label == "New value (mm)").set_value(8).run()
    next(b for b in ui.button if b.label == "Apply dimension and rebuild").click().run()
    assert not ui.exception and ui.session_state["project"].current.parent == first.id
    assert ui.session_state["project"].current.requirements.thickness == 8


def test_legacy_model_click_cannot_replace_manual_dimension_selection(monkeypatch):
    from streamlit.testing.v1 import AppTest

    click = {}

    def event(**kw):
        return SimpleNamespace(
            picked={"context": kw["data"]["context"], "field": click["field"]}
            if click
            else None
        )

    monkeypatch.setattr("fixture.dimensions.component", lambda: event)
    a, r = ready()
    p = Project(a, r)
    p.generate()
    ui = AppTest.from_file(str(Path("app.py").resolve()), default_timeout=45)
    ui.session_state["project"] = p
    ui.run()
    next(c for c in ui.checkbox if c.label == "Edit fixture dimensions").check().run()
    next(s for s in ui.selectbox if s.label == "Dimension to edit").select(
        "margin"
    ).run()
    assert (
        next(s for s in ui.selectbox if s.label == "Dimension to edit").value
        == "margin"
    )
    click["field"] = "thickness"
    ui.run()
    assert not ui.exception
    assert (
        next(s for s in ui.selectbox if s.label == "Dimension to edit").value
        == "margin"
    )
    assert (
        next(n for n in ui.number_input if n.label == "New value (mm)").value
        == r.margin
    )
