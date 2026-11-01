import json

import cadquery as cq
import pytest
from streamlit.testing.v1 import AppTest

from fixture.project import Project, ROOT
from fixture.step_export import prepare_step
from tests.test_geometry import ready


def button(ui, label):
    return next(x for x in ui.button if x.label == label)


def check(ui, label):
    return next(x for x in ui.checkbox if x.label == label)


def thickness(ui):
    return next(x for x in ui.number_input if x.label == "Fixture thickness (mm)")


def app(project):
    ui = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    ui.session_state["project"] = project
    ui.run()
    next(x for x in ui.selectbox if x.label == "Conversation mode").select(
        "Offline commands"
    ).run()
    return ui


def visible_meshes(ui):
    charts = ui.get("plotly_chart")
    assert len(charts) == 1
    return {
        t["name"]
        for t in json.loads(charts[0].proto.spec)["data"]
        if t["type"] == "mesh3d"
    }


def test_thickness_saves_before_generation_and_recovers_invalid_input(monkeypatch):
    a, r = ready()
    p = Project(a, r)
    ui = app(p)
    thickness(ui).set_value(8).run()
    assert not ui.exception and p.requirements.thickness == 8 and not p.revisions
    assert p.requirements.provenance["thickness"] == "user"
    assert (
        Project.load(ROOT / "artifacts" / p.id / "project.json").requirements.thickness
        == 8
    )
    thickness(ui).set_value(0).run()
    assert p.requirements.thickness == 8 and thickness(ui).value == 8
    assert any("greater than zero" in e.value for e in ui.error)

    def fail_save(self):
        raise OSError("Injected thickness save failure")

    monkeypatch.setattr(Project, "save", fail_save)
    thickness(ui).set_value(9).run()
    assert (
        not ui.exception and p.requirements.thickness == 8 and thickness(ui).value == 8
    )
    assert any("Injected thickness save failure" in e.value for e in ui.error)


@pytest.mark.parametrize(
    "mode",
    [
        "Select mounting face",
        "Select mounting holes",
        "Select openings / keep-clear areas",
    ],
)
def test_generation_leaves_source_picker_and_displays_generated_mesh(mode):
    a, r = ready()
    p = Project(a, r)
    ui = app(p)
    button(ui, mode).click().run()
    button(ui, "Generate Common mounting plate").click().run()
    assert not ui.exception and p.current
    assert not any(
        ui.session_state[k] for k in ("face_mode", "pick_mode", "access_mode")
    )
    names = visible_meshes(ui)
    assert set(p.current.meshes) <= names and "Source 1" in names
    button(ui, "View generated fixture").click().run()
    assert visible_meshes(ui) == set(p.current.meshes)
    assert not check(ui, "Source").value and check(ui, "Fixture").value
    button(ui, "View assembly").click().run()
    assert "Source 1" in visible_meshes(ui) and check(ui, "Fixture").value


def test_thickness_rebuild_and_restore_show_the_correct_real_cad():
    a, r = ready()
    p = Project(a, r)
    first = p.generate()
    ui = app(p)
    check(ui, "Fixture").uncheck().run()
    button(ui, "Select mounting holes").click().run()
    thickness(ui).set_value(8).run()
    assert p.current.id == first.id and p.requirements.thickness == 8
    assert any("Showing the 6 mm fixture" in c.value for c in ui.caption)
    button(ui, "Rebuild with this thickness").click().run()
    second = p.current
    assert not ui.exception and second.parent == first.id
    assert (
        second.requirements.thickness == 8
        and second.metrics["volume_mm3"] > first.metrics["volume_mm3"]
    )
    assert second.plan.interface_id == first.plan.interface_id
    assert set(second.meshes) <= visible_meshes(ui) and check(ui, "Fixture").value
    shape = cq.importers.importStep(str(prepare_step(second))).val()
    assert shape.isValid() and shape.BoundingBox().zlen == pytest.approx(8, abs=0.01)
    button(ui, "Select mounting face").click().run()
    next(s for s in ui.selectbox if s.label == "Revision history").select(first.id)
    button(ui, "Restore selected revision").click().run()
    assert not ui.exception and p.current.id == first.id and thickness(ui).value == 6
    assert set(first.meshes) <= visible_meshes(ui)


def test_locked_thickness_and_failed_rebuild_keep_last_valid_preview(monkeypatch):
    a, r = ready(locks=("thickness",))
    p = Project(a, r)
    first = p.generate()
    ui = app(p)
    assert thickness(ui).disabled
    p.requirements = r.model_copy(update={"locks": (), "thickness": 8})
    ui.run()
    button(ui, "Select mounting holes").click().run()

    def fail(*args, **kwargs):
        raise RuntimeError("Injected rebuild failure")

    monkeypatch.setattr("fixture.project.execute", fail)
    button(ui, "Rebuild with this thickness").click().run()
    assert not ui.exception and p.current.id == first.id
    assert "Injected rebuild failure" in p.error
    assert set(first.meshes) <= visible_meshes(ui)
