from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from fixture.contracts import Envelope
from fixture.face_picking import (
    FacePicks,
    pick_face,
    use_picked_face,
    face_surface,
    face_picker_figure,
)
from fixture.intake import local_points
from fixture.planning import compile_plan
from tests.test_geometry import ready


@pytest.mark.parametrize(
    "source", ["synthetic_motor.step", "sensor_bracket.step", "transformed_motor.step"]
)
def test_face_patches_follow_source_and_preserve_holes(source):
    a, r = ready(source)
    i = next(i for i in a.interfaces if i.id == r.interface_id)
    assert i.face_mesh and i.face_mesh.triangles
    assert abs(local_points(i.face_mesh.vertices, i)[:, 2]).max() < 1e-6
    legacy = i.model_copy(update={"face_mesh": None})
    patch = face_surface(a, legacy)
    assert patch.triangles
    assert abs(local_points(patch.vertices, i)[:, 2]).max() < 0.01
    # The rendered patches are actual source triangles, with no filled-in holes.
    source_facets = {
        tuple(sorted(tuple(a.mesh.vertices[v]) for v in t)) for t in a.mesh.triangles
    }
    assert all(
        tuple(sorted(tuple(patch.vertices[v]) for v in t)) in source_facets
        for t in patch.triangles
    )
    fig = face_picker_figure(a)
    assert {
        t.meta["interface_id"]
        for t in fig.data
        if t.meta and t.meta.get("pick_kind") == "face"
    } == {i.id for i in a.interfaces}


def test_face_ids_confirmation_frame_reset_and_locks():
    a, r = ready()
    old = next(i for i in a.interfaces if i.id == r.interface_id)
    other = next(i for i in a.interfaces if i.id != r.interface_id)
    picks = FacePicks()
    event = dict(context=picks.context, interface_id=other.id)
    picks = pick_face(a, picks, event)
    assert pick_face(a, picks, event) == picks
    for bad in (
        {**event, "context": "stale"},
        {**event, "interface_id": "missing"},
        {**event, "x": 0},
    ):
        with pytest.raises(ValueError):
            pick_face(a, picks, bad)
    with pytest.raises(ValueError, match="Confirm"):
        use_picked_face(a, r, picks, other.hole_ids, False)
    with pytest.raises(ValueError, match="detected fastener"):
        use_picked_face(a, r, picks, old.hole_ids, True)
    envelope = Envelope(
        id="tool", minimum=(0, 0, -10), maximum=(1, 1, 1), purpose="Old-frame access"
    )
    pending = r.model_copy(
        update={
            "rear_passages": ("old-profile",),
            "envelopes": (envelope,),
            "through_access_required": True,
        }
    )
    changed = use_picked_face(a, pending, picks, other.hole_ids, True)
    assert changed.interface_id == other.id and changed.mounting_confirmed
    assert (
        changed.rear_passages == ()
        and changed.envelopes == ()
        and changed.through_access_required
    )
    for field in ("interface_id", "envelopes"):
        with pytest.raises(ValueError, match="locked"):
            use_picked_face(
                a,
                pending.model_copy(update={"locks": (field,)}),
                picks,
                other.hole_ids,
                True,
            )


def test_face_button_immediate_selection_and_mode_switch(monkeypatch):
    from streamlit.testing.v1 import AppTest

    events = []

    def component(**kwargs):
        event = events.pop(0) if events else None
        if event:
            event.setdefault("sequence", kwargs["data"]["sequence"] + 1)
            if "hole_ids" in event:
                event["hole_ids"] = tuple(
                    dict.fromkeys((*kwargs["data"]["hole_ids"], *event["hole_ids"]))
                )
        return SimpleNamespace(picked=event)

    monkeypatch.setattr("fixture.mounting_picker.picker_component", lambda: component)
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45
    ).run()
    next(b for b in app.button if b.label == "Load example").click().run()
    project = app.session_state["project"]
    original = project.requirements
    next(b for b in app.button if b.label == "Select mounting face").click().run()
    assert not app.exception
    picks = app.session_state["mounting_picks"]
    interface = next(
        i for i in project.analysis.interfaces if i.id == original.interface_id
    )
    events.append(dict(context=picks.context, interface_id=interface.id))
    app.run()
    assert not app.exception
    saved = app.session_state["project"].requirements
    assert saved.mounting_confirmed and saved.mounting_hole_ids == ()
    assert saved.part_attachment == "unselected"
    assert not any(b.label == "Use this mounting face" for b in app.button)
    next(b for b in app.button if b.label == "Select mounting holes").click().run()
    assert not app.session_state["mounting_picks"].hole_ids
    next(b for b in app.button if b.label == "View assembly").click().run()
    assert not app.exception and app.session_state["project"].requirements == saved


def test_rear_error_is_reported_not_mislabeled_as_absent(monkeypatch):
    from fixture.agent import planner_context

    a, r = ready()

    def failed(*args):
        raise ValueError("Bad measured profile")

    monkeypatch.setattr("fixture.clearance.passage_options", failed)
    context = planner_context(a, r)
    assert context["rear_clearance_error"] == "Bad measured profile"
    assert context["rear_clearance_profiles"] == []
    assert all("face_mesh" not in i for i in context["interfaces"])


def test_supporting_plane_fallback_encloses_points_and_padding(monkeypatch):
    from fixture.clearance import stable_profile, _region

    # Nearly redundant edges like segmented planar terminal faces.
    xy = np.array(
        [[-3, -1], [-3 + 1e-11, -1], [-2, -1 + 1e-12], [3, -1], [3, 1], [-3, 1]]
    )
    polygon = stable_profile(xy, 0.3)
    # Force the malformed offset that previously hid all connector profiles.
    monkeypatch.setattr(
        "fixture.clearance.offset_profile",
        lambda *args: np.array([[-3.3, -1.3], [3.3, 1.3], [3.3, -1.3], [-3.3, 1.3]]),
    )
    op = _region(np.column_stack((xy, np.full(len(xy), -2))), 0.3, 0)
    assert op.shape == "prism"
    assert op.provenance["stable_envelope"] == "derived"
    assert np.allclose(np.array(op.profile) + op.origin[:2], polygon)
    for n, p in enumerate(polygon):
        q = polygon[(n + 1) % len(polygon)]
        normal = np.array([q[1] - p[1], p[0] - q[0]])
        normal /= np.linalg.norm(normal)
        assert np.max(xy @ normal) + 0.3 <= p @ normal + 1e-8


def test_plate_rear_relief_is_versioned(tmp_path):
    from tests.test_passages import shallow_source

    a, r, profile = shallow_source(tmp_path)
    plate = r.model_copy(update={"composition": "plate", "rear_passages": (profile,)})
    assert compile_plan(a, plate).version == 10
    with pytest.raises(ValueError, match="version 7"):
        compile_plan(a, plate, compiler_version=6)
