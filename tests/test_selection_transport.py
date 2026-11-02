from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from fixture.project import Project
from tests.test_geometry import ROOT, ready


def test_large_geometry_only_sent_for_a_new_browser_request(monkeypatch):
    a, r = ready()
    p = Project(a, r)
    payloads = []

    def component(**kwargs):
        payloads.append(kwargs["data"])
        return SimpleNamespace(picked=None)

    monkeypatch.setattr("fixture.mounting_picker.picker_component", lambda: component)
    ui = AppTest.from_string(
        'import streamlit as st\nfrom fixture.mounting_picker import render_mounting_picker\nrender_mounting_picker(st.session_state.project,"holes")'
    )
    ui.session_state.project = p
    ui.run()
    assert payloads[-1]["figure"] is None
    key = "mounting-picker-" + p.id
    ui.session_state[key] = {"geometry_request": "browser-1"}
    ui.run()
    figure = payloads[-1]["figure"]
    assert len(figure) > 1000 and payloads[-1]["geometry_token"] == "browser-1"
    ui.session_state[key] = {
        "geometry_request": "browser-1",
        "geometry_loaded": "browser-1",
    }
    ui.run()
    assert payloads[-1]["figure"] is None
    # Reopening or reloading the browser must fetch the geometry again.
    ui.session_state[key] = {
        "geometry_request": "browser-2",
        "geometry_loaded": "browser-1",
    }
    ui.run()
    assert (
        payloads[-1]["figure"] == figure
        and payloads[-1]["geometry_token"] == "browser-2"
    )
    assert not ui.exception


def test_selection_saves_reuse_immutable_mesh_json_and_invalidate_replacement(
    monkeypatch,
):
    a, r = ready()
    p = Project(a, r)
    serialized = []
    original = type(a).model_dump_json

    def dump(self, *args, **kwargs):
        serialized.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(a), "model_dump_json", dump)
    p.save()
    for count in range(4):
        p.requirements = r.model_copy(
            update={"mounting_hole_ids": a.interfaces[0].hole_ids[:count]}
        )
        p.save()
    assert len(serialized) == 1
    restored = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert restored.analysis == a and restored.requirements == p.requirements
    p.analysis = a.model_copy(update={"source_name": "Changed name.step"})
    p.save()
    assert len(serialized) == 2
    assert (
        Project.load(ROOT / "artifacts" / p.id / "project.json").analysis.source_name
        == "Changed name.step"
    )
