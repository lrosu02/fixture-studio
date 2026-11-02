from types import SimpleNamespace

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from fixture.custom_openings import opening_candidate
from fixture.opening_controls import apply_opening_event, opening_state
from fixture.project import Project
from tests.test_geometry import ready


@pytest.fixture(scope="module")
def built_fixture():
    a, r = ready("synthetic_motor.step", thickness=6.0)
    p = Project(a, r)
    p.generate()
    return p


def event_for(project, sequence=1):
    revision = project.current
    for body, mesh in revision.meshes.items():
        vertices = np.asarray(mesh.vertices)
        for index, tri in enumerate(mesh.triangles):
            points = vertices[list(tri)]
            normal = np.cross(points[1] - points[0], points[2] - points[0])
            if (
                np.linalg.norm(normal)
                and abs(normal[2]) / np.linalg.norm(normal) > 1 - 1e-8
            ):
                return dict(
                    context=f"{project.id}:{revision.id}",
                    revision_id=revision.id,
                    sequence=sequence,
                    body=body,
                    triangle=index,
                    point=points.mean(axis=0).tolist(),
                )
    raise AssertionError("Expected a flat fixture face")


def button(ui, label):
    return next(x for x in ui.button if x.label == label)


def opening_ui(monkeypatch, built_fixture):
    p = Project(built_fixture.analysis, built_fixture.requirements)
    p.revisions = list(built_fixture.revisions)
    p.active_id = built_fixture.active_id
    p.stage = "presented"
    events, payloads, builds = [], [], []

    def component(**kwargs):
        payloads.append(kwargs["data"])
        return SimpleNamespace(picked=events.pop(0) if events else None)

    def build(project, candidate, description):
        builds.append((candidate, description))

    def forbidden_save(self):
        raise AssertionError("Preview/edit controls must not save the project")

    monkeypatch.setattr("fixture.opening_controls.opening_component", lambda: component)
    monkeypatch.setattr(Project, "save", forbidden_save)
    ui = AppTest.from_string(
        "import streamlit as st\n"
        "from fixture.opening_controls import render_opening_view\n"
        "render_opening_view(st.session_state.project, st.session_state.build, "
        "enabled=True, source=False, fixture=True, evidence=False, dimensions=False, "
        "envelopes=False, previous=None)\n",
        default_timeout=30,
    )
    ui.session_state["project"] = p
    ui.session_state["build"] = build
    ui.run()
    return ui, p, events, payloads, builds


def test_pick_and_diameter_are_drafts_until_explicit_rebuild(
    monkeypatch, built_fixture
):
    ui, p, events, payloads, builds = opening_ui(monkeypatch, built_fixture)
    original, revision = p.requirements, p.current
    assert not ui.exception and button(ui, "Add opening and rebuild").disabled
    click = event_for(p)
    events.append(click)
    ui.run()
    next(x for x in ui.number_input if x.label == "Opening diameter (mm)").set_value(
        12
    ).run()
    assert not ui.exception and not builds
    assert p.requirements == original and p.current is revision
    assert not button(ui, "Add opening and rebuild").disabled
    assert payloads[-1]["preview"]["center"] == tuple(click["point"])
    button(ui, "Add opening and rebuild").click().run()
    assert len(builds) == 1 and not ui.exception
    candidate = builds[0][0]
    assert candidate.fixture_openings[0].diameter == 12
    assert candidate.fixture_openings[0].center == tuple(click["point"])
    assert p.requirements == original and p.current is revision
    button(ui, "Clear opening position").click().run()
    events.append(
        click
    )  # An old component acknowledgement cannot restore a cleared draft.
    ui.run()
    assert button(ui, "Add opening and rebuild").disabled
    assert not ui.exception


def test_resize_remove_and_failed_rebuild_keep_saved_design(monkeypatch, built_fixture):
    ui, p, events, _, builds = opening_ui(monkeypatch, built_fixture)
    p.requirements = opening_candidate(p, event_for(p), 8)
    original, revision = p.requirements, p.current
    ui.run()
    next(
        x for x in ui.number_input if x.label == "Diameter · Opening 1 (mm)"
    ).set_value(14).run()
    assert not builds and p.requirements == original
    button(ui, "Resize and rebuild").click().run()
    assert builds[-1][0].fixture_openings[0].diameter == 14
    assert (
        builds[-1][0].fixture_openings[0].center == original.fixture_openings[0].center
    )
    button(ui, "Remove and rebuild").click().run()
    assert builds[-1][0].fixture_openings == ()
    assert p.requirements == original and p.current is revision

    def fail_build(project, candidate, description):
        raise ValueError("Injected native check failure")

    ui.session_state["build"] = fail_build
    events.append(event_for(p, 2))
    ui.run()
    button(ui, "Add opening and rebuild").click().run()
    assert not ui.exception and any(
        "Injected native check failure" in x.value for x in ui.error
    )
    assert p.requirements == original and p.current is revision
    p.requirements = original.model_copy(update={"locks": ("fixture_openings",)})
    ui.run()
    assert button(ui, "Add opening and rebuild").disabled
    assert button(ui, "Resize and rebuild").disabled
    assert button(ui, "Remove and rebuild").disabled
    assert not ui.exception


def test_wrong_project_stale_sequence_and_invalid_triangle_are_rejected(
    monkeypatch, built_fixture
):
    monkeypatch.setattr("fixture.opening_controls.st.session_state", {})
    p = built_fixture
    click = event_for(p, 3)
    apply_opening_event(p, {**click, "context": "another-project"})
    assert opening_state(p)["event"] is None
    apply_opening_event(p, click)
    assert opening_state(p)["event"] == click
    apply_opening_event(p, {**click, "sequence": 2, "point": [9, 9, 9]})
    assert opening_state(p)["event"] == click
    apply_opening_event(p, {**click, "sequence": 4, "revision_id": "old"})
    assert opening_state(p)["event"] is None and "older" in opening_state(p)["error"]
    apply_opening_event(p, {**click, "sequence": 5, "triangle": 10**9})
    assert opening_state(p)["event"] is None and "triangle" in opening_state(p)["error"]
