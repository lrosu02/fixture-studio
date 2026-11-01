from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from fixture.project import Project
from tests.test_geometry import ready, ROOT


def button(ui, label):
    return next(x for x in ui.button if x.label == label)


def picker_ui(monkeypatch, **updates):
    a, r = ready("mixed_hole_sizes.step", **updates)
    p = Project(a, r)
    events = {"face": [], "holes": []}
    payloads = {"face": [], "holes": []}

    def component(**kwargs):
        data = kwargs["data"]
        kind = data["mode"]
        payloads[kind].append(data)
        event = events[kind].pop(0) if events[kind] else None
        if event:
            event.setdefault("sequence", data["sequence"] + 1)
            # Browser sends a full snapshot, including previous rapid clicks.
            if kind == "holes":
                event["hole_ids"] = tuple(
                    dict.fromkeys((*data["hole_ids"], *event["hole_ids"]))
                )
        return SimpleNamespace(picked=event)

    monkeypatch.setattr("fixture.mounting_picker.picker_component", lambda: component)
    ui = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45)
    ui.session_state["project"] = p
    ui.run()
    return ui, p, events, payloads


def test_immediate_selections_survive_switches_without_automatic_holes(monkeypatch):
    ui, p, events, payloads = picker_ui(monkeypatch, mounting_confirmed=False)
    original = p.requirements
    face = next(i for i in p.analysis.interfaces if i.id == original.interface_id)
    button(ui, "Select mounting face").click().run()
    assert p.requirements == original
    events["face"].append(
        dict(context=ui.session_state["mounting_picks"].context, interface_id=face.id)
    )
    ui.run()
    assert not ui.exception
    assert p.requirements.mounting_confirmed and p.requirements.mounting_hole_ids == ()
    assert p.requirements.part_attachment == "unselected"
    retention = next(
        x for x in ui.selectbox if x.label == "How should the part be held?"
    )
    assert "Screws through selected part holes" not in retention.options
    assert not any("Use this mounting face" == x.label for x in ui.button)

    button(ui, "Select mounting holes").click().run()
    assert not ui.session_state["mounting_picks"].hole_ids
    context = ui.session_state["mounting_picks"].context
    for hole in face.hole_ids[:2]:
        events["holes"].append(
            dict(context=context, interface_id=face.id, hole_ids=(hole,))
        )
        ui.run()
        assert not ui.exception
    assert p.requirements.mounting_hole_ids == face.hole_ids[:2]
    assert ui.session_state["mounting_picks"].context == context
    assert p.requirements.part_attachment == "screws"
    assert (
        "Screws through selected part holes"
        in next(
            x for x in ui.selectbox if x.label == "How should the part be held?"
        ).options
    )
    messages = list(p.messages)
    events["holes"].append(
        dict(context=context, interface_id=face.id, hole_ids=face.hole_ids[:2])
    )
    ui.run()
    assert p.messages == messages  # Replayed additions do not write duplicate choices.
    saved = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert saved.requirements == p.requirements and not p.revisions

    button(ui, "Select mounting face").click().run()
    assert ui.session_state["mounting_picks"].interface_id == face.id
    assert payloads["face"][-1]["hole_ids"] == list(face.hole_ids[:2])
    button(ui, "Select mounting holes").click().run()
    assert ui.session_state["mounting_picks"].hole_ids == face.hole_ids[:2]
    assert payloads["holes"][-1]["interface_id"] == face.id
    assert payloads["holes"][-1]["figure"] == payloads["face"][-1]["figure"]
    current = p.requirements
    button(ui, "View assembly").click().run()
    assert p.requirements == current
    assert not ui.session_state["pick_mode"]
    assert not any(x.label == "Use these mounting holes" for x in ui.button)


def test_explicit_removal_clear_and_another_face_invalidate_old_events(monkeypatch):
    ui, p, events, _ = picker_ui(monkeypatch)
    face = next(i for i in p.analysis.interfaces if i.id == p.requirements.interface_id)
    button(ui, "Select mounting holes").click().run()
    context = ui.session_state["mounting_picks"].context
    events["holes"].append(
        dict(context=context, interface_id=face.id, hole_ids=face.hole_ids[:2])
    )
    ui.run()
    next(
        x for x in ui.multiselect if x.label == "Selected holes — remove with ×"
    ).unselect(face.hole_ids[1]).run()
    assert p.requirements.mounting_hole_ids == (face.hole_ids[0],)
    assert ui.session_state["mounting_picks"].context != context
    button(ui, "Clear hole selection").click().run()
    assert (
        not p.requirements.mounting_hole_ids
        and p.requirements.part_attachment == "unselected"
    )
    events["holes"].append(
        dict(context=context, interface_id=face.id, hole_ids=face.hole_ids[:2])
    )
    ui.run()
    assert not p.requirements.mounting_hole_ids
    assert not any("older selection" in x.value for x in ui.warning)
    button(ui, "Select mounting face").click().run()
    other = next(i for i in p.analysis.interfaces if i.id != face.id)
    events["face"].append(
        dict(context=ui.session_state["mounting_picks"].context, interface_id=other.id)
    )
    ui.run()
    assert p.requirements.interface_id == other.id
    assert (
        not p.requirements.mounting_hole_ids
        and p.requirements.part_attachment == "unselected"
    )
    assert not ui.exception


def test_locked_choices_and_save_failure_preserve_accepted_requirements(monkeypatch):
    ui, p, events, _ = picker_ui(monkeypatch, locks=("mounting_hole_ids",))
    original = p.requirements
    face = next(i for i in p.analysis.interfaces if i.id == original.interface_id)
    button(ui, "Select mounting holes").click().run()
    events["holes"].append(
        dict(
            context=ui.session_state["mounting_picks"].context,
            interface_id=face.id,
            hole_ids=(face.hole_ids[0],),
        )
    )
    ui.run()
    assert not ui.exception and p.requirements == original and not p.messages
    assert any("locked" in x.value for x in ui.warning)
    assert not ui.session_state["mounting_picks"].hole_ids

    p.requirements = original.model_copy(update={"locks": ()})
    original = p.requirements

    def fail_save(self):
        raise OSError("Injected selection save failure")

    monkeypatch.setattr(Project, "save", fail_save)
    button(ui, "Select mounting face").click().run()
    other = next(i for i in p.analysis.interfaces if i.id != face.id)
    events["face"].append(
        dict(context=ui.session_state["mounting_picks"].context, interface_id=other.id)
    )
    ui.run()
    assert not ui.exception and p.requirements == original and not p.messages
    assert any("Injected selection save failure" in x.value for x in ui.warning)


def test_examples_start_collapsed():
    ui = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    assert not ui.exception
    examples = next(x for x in ui.expander if x.label == "Try an example")
    assert not examples.proto.expanded
    assert any(x.label == "Bundled specimen" for x in examples.selectbox)
    assert any(x.label == "Load example" for x in examples.button)


def test_selected_face_outline_excludes_mesh_diagonals_and_hole_rim():
    import numpy as np
    from fixture.contracts import Mesh
    from fixture.hole_picker import outer_boundary_points

    # A square face with a square opening, triangulated around the opening.
    vertices = (
        (-3, -3, 0),
        (3, -3, 0),
        (3, 3, 0),
        (-3, 3, 0),
        (-1, -1, 0),
        (1, -1, 0),
        (1, 1, 0),
        (-1, 1, 0),
    )
    triangles = (
        (0, 1, 5),
        (0, 5, 4),
        (1, 2, 6),
        (1, 6, 5),
        (2, 3, 7),
        (2, 7, 6),
        (3, 0, 4),
        (3, 4, 7),
    )
    outline = outer_boundary_points(Mesh(vertices=vertices, triangles=triangles))
    segments = outline.reshape(-1, 3, 3)[:, :2]
    assert len(segments) == 4
    assert all(
        np.all(np.abs(segment[:, 0]) == 3) or np.all(np.abs(segment[:, 1]) == 3)
        for segment in segments
    )
    assert all(np.linalg.norm(segment[1] - segment[0]) == 6 for segment in segments)


def test_access_view_keeps_only_explicit_mounting_hole_highlights():
    import json
    from fixture.access_controls import access_figure

    a, r = ready("mixed_hole_sizes.step")
    face = next(i for i in a.interfaces if i.id == r.interface_id)
    chosen = face.hole_ids[:2]
    r = r.model_copy(update={"mounting_hole_ids": chosen})
    figure = json.loads(access_figure("explicit-highlights-" + str(chosen), a, r))
    assert any(t.get("name") == "Selected mounting face" for t in figure["data"])
    assert {
        t["meta"]["hole_id"] for t in figure["data"] if t.get("meta", {}).get("hole_id")
    } == set(chosen)


def test_generate_refreshes_selection_and_blocks_missing_choices(monkeypatch):
    calls = []

    def generate(project, reviewer, mode, requirements, change, progress):
        calls.append(requirements)

    monkeypatch.setattr("fixture.workflow.generate_with_feedback", generate)
    ui, p, events, _ = picker_ui(monkeypatch, mounting_confirmed=False)
    button(ui, "Generate Common mounting plate").click().run()
    assert not calls and not p.revisions and not ui.exception
    assert any("Before generating" in x.value for x in ui.warning)
    button(ui, "Select mounting holes").click().run()
    face = next(i for i in p.analysis.interfaces if i.id == p.requirements.interface_id)
    events["holes"].append(
        dict(
            context=ui.session_state["mounting_picks"].context,
            interface_id=face.id,
            hole_ids=(face.hole_ids[0],),
        )
    )
    button(ui, "Generate Common mounting plate").click().run()
    assert not ui.exception and len(calls) == 1
    assert calls[0].mounting_confirmed and calls[0].mounting_hole_ids == (
        face.hole_ids[0],
    )


def test_first_manufacturing_edit_after_selection_is_saved(monkeypatch):
    ui, p, events, _ = picker_ui(monkeypatch, mounting_confirmed=False)
    button(ui, "Select mounting holes").click().run()
    face = next(i for i in p.analysis.interfaces if i.id == p.requirements.interface_id)
    events["holes"].append(
        dict(
            context=ui.session_state["mounting_picks"].context,
            interface_id=face.id,
            hole_ids=(face.hole_ids[0],),
        )
    )
    ui.run()
    next(x for x in ui.selectbox if x.label == "Manufacturing method").select(
        "3D printing"
    ).run()
    button(ui, "Save manufacturing").click().run()
    assert not ui.exception and p.requirements.fabrication == "3D printing"
    assert p.requirements.mounting_hole_ids == (face.hole_ids[0],)
    assert not p.revisions


def test_newer_snapshot_wins_over_delayed_first_hole_and_survives_mode_changes(
    monkeypatch,
):
    ui, p, events, payloads = picker_ui(monkeypatch)
    face = next(i for i in p.analysis.interfaces if i.id == p.requirements.interface_id)
    button(ui, "Select mounting holes").click().run()
    context = ui.session_state["mounting_picks"].context
    events["holes"].append(
        dict(context=context, sequence=4, interface_id=face.id, hole_ids=face.hole_ids)
    )
    ui.run()
    messages = list(p.messages)
    events["holes"].append(
        dict(
            context=context,
            sequence=1,
            interface_id=face.id,
            hole_ids=face.hole_ids[:1],
        )
    )
    ui.run()
    assert p.requirements.mounting_hole_ids == face.hole_ids
    assert p.messages == messages
    figure = payloads["holes"][-1]["figure"]
    for _ in range(3):
        button(ui, "Select mounting face").click().run()
        assert payloads["face"][-1]["figure"] == figure
        button(ui, "Select mounting holes").click().run()
        assert payloads["holes"][-1]["context"] == context
        assert p.requirements.mounting_hole_ids == face.hole_ids
    saved = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert saved.requirements.mounting_hole_ids == face.hole_ids
    assert not p.revisions and not ui.exception
