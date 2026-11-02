from types import SimpleNamespace

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from fixture.custom_openings import opening_candidate
from fixture.opening_controls import apply_opening_event, opening_state
from fixture.project import Project
from fixture.contracts import FixtureOpening
from tests.test_geometry import ready, ROOT


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


def pending_setup(project, count=1, composition=None):
    first = opening_candidate(project, event_for(project), 10).fixture_openings[0]
    openings = tuple(
        FixtureOpening.model_validate(
            {
                **first.model_dump(),
                "id": f"saved-opening-{number}",
                "diameter": float(10 + 4 * number),
                "needs_placement": True,
            }
        )
        for number in range(count)
    )
    changes = {"fixture_openings": openings}
    if composition:
        changes["composition"] = composition
    project.requirements = project.requirements.model_copy(update=changes)
    project.revisions = [
        project.current.model_copy(update={"requirements": project.requirements})
    ]
    return openings


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


def test_pending_openings_reuse_ids_and_diameters_one_at_a_time(
    monkeypatch, built_fixture
):
    ui, p, events, payloads, builds = opening_ui(monkeypatch, built_fixture)
    openings = pending_setup(p, count=2)
    saved = p.requirements
    ui.run()
    pending = next(x for x in ui.expander if "2 need placement" in x.label)
    assert pending.proto.expanded
    assert not any(x.label == "Resize and rebuild" for x in ui.button)
    assert not any(x.label.startswith("Diameter · Opening") for x in ui.number_input)
    assert any("reference only" in x.value for x in ui.caption)
    next(x for x in ui.button if x.label == "Place on this fixture").click().run()
    assert not ui.exception and not builds and p.requirements == saved
    state = ui.session_state["fixture-opening-draft-" + p.id]
    assert state["opening_id"] == openings[0].id
    assert (
        next(x for x in ui.number_input if x.label == "Opening diameter (mm)").value
        == 10
    )
    assert button(ui, "Place opening and rebuild").disabled
    events.append(event_for(p, payloads[-1]["sequence"] + 1))
    ui.run()
    button(ui, "Place opening and rebuild").click().run()
    candidate = builds[-1][0]
    assert len(candidate.fixture_openings) == 2
    assert [x.id for x in candidate.fixture_openings] == [x.id for x in openings]
    assert not candidate.fixture_openings[0].needs_placement
    assert candidate.fixture_openings[1].needs_placement
    assert p.requirements == saved

    # Accept the first UI candidate without running native CAD in this UI test.
    p.requirements = candidate
    p.revisions.append(
        p.current.model_copy(
            update={
                "id": "placed-first-ui-revision",
                "parent": p.active_id,
                "requirements": candidate,
            }
        )
    )
    p.active_id = "placed-first-ui-revision"
    ui.run()
    button(ui, "Place on this fixture").click().run()
    state = ui.session_state["fixture-opening-draft-" + p.id]
    assert state["opening_id"] == openings[1].id
    assert (
        next(x for x in ui.number_input if x.label == "Opening diameter (mm)").value
        == 14
    )
    assert not state["event"]
    assert not ui.exception


def test_pending_removal_and_reposition_failure_preserve_saved_state(
    monkeypatch, built_fixture
):
    ui, p, events, payloads, builds = opening_ui(monkeypatch, built_fixture)
    opening = pending_setup(p)[0]
    saved, revision = p.requirements, p.current
    ui.run()
    button(ui, "Remove and rebuild").click().run()
    assert builds[-1][0].fixture_openings == ()
    assert p.requirements == saved and p.current is revision
    button(ui, "Place on this fixture").click().run()
    events.append(event_for(p, payloads[-1]["sequence"] + 1))
    ui.run()
    next(x for x in ui.number_input if x.label == "Opening diameter (mm)").set_value(
        12
    ).run()

    def fail_build(project, candidate, description):
        raise ValueError("Injected placement failure")

    ui.session_state["build"] = fail_build
    before = dict(ui.session_state["fixture-opening-draft-" + p.id])
    button(ui, "Place opening and rebuild").click().run()
    after = ui.session_state["fixture-opening-draft-" + p.id]
    assert after["opening_id"] == opening.id
    assert after["event"] == before["event"] and after["diameter"] == 12
    assert p.requirements == saved and p.current is revision
    assert any("Injected placement failure" in x.value for x in ui.error)
    assert not ui.exception


def test_pending_pick_requires_new_type_but_intent_can_be_removed(
    monkeypatch, built_fixture
):
    ui, p, _, _, builds = opening_ui(monkeypatch, built_fixture)
    pending_setup(p)
    p.requirements = p.requirements.model_copy(update={"composition": "bridge"})
    saved = p.requirements
    ui.run()
    assert button(ui, "Place on this fixture").disabled
    assert button(ui, "Add opening and rebuild").disabled
    button(ui, "Remove and rebuild").click().run()
    assert builds[-1][0].fixture_openings == ()
    assert builds[-1][0].composition == "bridge"
    assert p.requirements == saved and not ui.exception


def test_app_failed_placement_keeps_picker_and_explains_bridge_export(
    monkeypatch, built_fixture
):
    _, p, events, payloads, _ = opening_ui(monkeypatch, built_fixture)
    opening = pending_setup(p, composition="bridge")[0]
    saved, revision = p.requirements, p.current

    def fail_generate(project, reviewer, mode, requirements, change, progress):
        project.error = "Injected failed opening rebuild"

    monkeypatch.setattr("fixture.workflow.generate_with_feedback", fail_generate)
    ui = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45)
    ui.session_state.project = p
    ui.run()
    assert not ui.exception
    assert any("absent from this STEP" in x.value for x in ui.warning)
    assert any("mounting normal pointing up" in x.value for x in ui.info)
    assert any(
        "Switching fixture type keeps saved opening sizes" in x.value
        for x in ui.caption
    )
    button(ui, "Place next opening").click().run()
    assert ui.session_state["opening_mode"]
    events.append(event_for(p, payloads[-1]["sequence"] + 1))
    ui.run()
    before = dict(ui.session_state["fixture-opening-draft-" + p.id])
    button(ui, "Place opening and rebuild").click().run()
    after = ui.session_state["fixture-opening-draft-" + p.id]
    assert ui.session_state["opening_mode"]
    assert after["opening_id"] == opening.id and after["event"] == before["event"]
    assert p.requirements == saved and p.current is revision
    assert p.error == "Injected failed opening rebuild" and not ui.exception
