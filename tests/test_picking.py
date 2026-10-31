import numpy as np
import pytest
from fixture.picking import (
    HolePicks,
    add_picked_holes,
    retain_picked_holes,
    use_picked_holes,
)
from fixture.viewer import hole_picker_figure, assembly_figure
from fixture.project import Project
from tests.test_geometry import ready


def click(picks, interface, hole=None, **extra):
    return dict(
        context=picks.context,
        interface_id=interface.id,
        hole_ids=(hole or interface.hole_ids[0],),
        **extra,
    )


def test_additions_are_idempotent_and_removal_invalidates_old_events():
    a, r = ready()
    i = next(i for i in a.interfaces if i.id == r.interface_id)
    picks = HolePicks()
    picks = add_picked_holes(a, picks, click(picks, i))
    assert picks.hole_ids == (i.hole_ids[0],)
    with pytest.raises(ValueError, match="not in the current"):
        add_picked_holes(a, picks, click(picks, i, "invented-hole"))
    with pytest.raises(ValueError, match="older selection"):
        add_picked_holes(a, HolePicks(), click(picks, i))
    with pytest.raises(ValueError):
        add_picked_holes(a, picks, click(picks, i, x=999))
    other = next(j for j in a.interfaces if j.id != i.id)
    with pytest.raises(ValueError, match="one mounting face"):
        add_picked_holes(a, picks, click(picks, other))
    assert add_picked_holes(a, picks, click(picks, i)) == picks
    old_event = click(picks, i)
    picks = retain_picked_holes(picks, ())
    assert picks.hole_ids == () and picks.interface_id is None
    with pytest.raises(ValueError, match="older selection"):
        add_picked_holes(a, picks, old_event)
    assert add_picked_holes(a, picks, click(picks, other)).interface_id == other.id


def test_holes_on_a_new_face_clear_old_frame_regions_and_respect_locks():
    from fixture.contracts import AccessSelection, Envelope

    a, r = ready()
    old = next(i for i in a.interfaces if i.id == r.interface_id)
    other = next(i for i in a.interfaces if i.id != old.id and i.hole_ids)
    r = r.model_copy(
        update={
            "mounting_hole_ids": old.hole_ids[:1],
            "envelopes": (
                Envelope(
                    id="old-frame",
                    minimum=(-2, -2, -4),
                    maximum=(2, 2, 1),
                    purpose="Old-frame access",
                ),
            ),
            "rear_passages": ("rear-profile-0",),
            "access_selections": (AccessSelection(feature_id="face:" + old.id),),
        }
    )
    same = use_picked_holes(
        a, r, HolePicks(interface_id=old.id, hole_ids=old.hole_ids[:1]), True
    )
    assert (
        same.envelopes == r.envelopes and same.access_selections == r.access_selections
    )
    picks = HolePicks(interface_id=other.id, hole_ids=other.hole_ids[:1])
    changed = use_picked_holes(a, r, picks, True)
    assert (
        changed.interface_id == other.id and changed.mounting_hole_ids == picks.hole_ids
    )
    assert (
        not changed.envelopes
        and not changed.rear_passages
        and not changed.access_selections
    )
    with pytest.raises(ValueError, match="envelopes is locked"):
        use_picked_holes(a, r.model_copy(update={"locks": ("envelopes",)}), picks, True)
    assert r.envelopes and r.interface_id == old.id


@pytest.mark.parametrize(
    "name",
    [
        "synthetic_motor.step",
        "sensor_bracket.step",
        "transformed_motor.step",
        "mixed_hole_sizes.step",
    ],
)
def test_picker_positions_follow_measured_source_pose(name):
    a, _ = ready(name)
    fig = hole_picker_figure(a, HolePicks())
    assert len(fig.data) - 1 == sum(len(i.hole_ids) for i in a.interfaces)
    for trace in fig.data[1:]:
        i = next(i for i in a.interfaces if i.id == trace.meta["interface_id"])
        idx = i.hole_ids.index(trace.meta["hole_id"])
        c = np.array(i.centers[idx]) + [0, 0, -0.06]
        expected = c @ np.array([i.x, i.y, i.z]) + i.origin
        assert [trace.x[-1], trace.y[-1], trace.z[-1]] == pytest.approx(expected)
        world = np.array([trace.x[:49], trace.y[:49], trace.z[:49]]).T
        assert np.linalg.norm(world - expected, axis=1) == pytest.approx(
            np.full(49, i.diameters[idx] / 2)
        )


def test_picked_subset_drives_native_geometry_and_persists():
    a, r = ready()
    i = next(i for i in a.interfaces if i.id == r.interface_id)
    picks = HolePicks()
    for hid in i.hole_ids[:2]:
        picks = add_picked_holes(a, picks, click(picks, i, hid))
    with pytest.raises(ValueError, match="stationary"):
        use_picked_holes(a, r, picks, False)
    with pytest.raises(ValueError, match="at least one"):
        use_picked_holes(a, r, HolePicks(), True)
    with pytest.raises(ValueError, match="locked"):
        use_picked_holes(
            a, r.model_copy(update={"locks": ("mounting_hole_ids",)}), picks, True
        )
    selected = use_picked_holes(a, r, picks, True)
    assert selected.provenance["mounting_hole_ids"] == "user"
    p = Project(a, selected)
    revision = p.generate()
    assert revision.metrics["hole_count"] == 2
    assert all(c.result != "failed" for c in revision.checks)
    restored = Project.load(
        __import__("pathlib").Path(revision.artifact).parent.parent / "project.json"
    )
    assert restored.requirements.mounting_hole_ids == picks.hole_ids
    assert restored.requirements.mounting_confirmed
    assert len(i.hole_ids) == 4  # Source analysis was not edited.


def test_mixed_size_evidence_stays_identifiable_after_selection():
    a, r = ready("mixed_hole_sizes.step")
    i = next(i for i in a.interfaces if i.id == r.interface_id)
    assert sorted(i.diameters) == pytest.approx([3, 3, 5, 5])
    empty = HolePicks()
    initial = hole_picker_figure(a, empty)
    picked = add_picked_holes(a, empty, click(empty, i))
    selected = hole_picker_figure(a, picked)
    styles = {}
    for before, after in zip(initial.data[1:], selected.data[1:]):
        face = next(f for f in a.interfaces if f.id == before.meta["interface_id"])
        d = round(face.diameters[face.hole_ids.index(before.meta["hole_id"])], 3)
        # Same measured sizes on different faces have one color; a pick cannot
        # replace size evidence with a common selection color.
        assert styles.setdefault(d, before.line.color) == before.line.color
        assert after.line.color == before.line.color
        if after.meta["hole_id"] in picked.hole_ids and face.id == picked.interface_id:
            assert after.marker.symbol[-1] != before.marker.symbol[-1]
            assert after.line.width > before.line.width
        elif face.id != picked.interface_id:
            assert after.opacity < before.opacity
    assert len(set(styles.values())) == len(styles) == 2
    assembly = assembly_figure(a, i.id)
    legends = [t.name for t in assembly.data if t.type == "scatter3d" and t.showlegend]
    assert set(legends) == {"Ø 3.000 mm measured", "Ø 5.000 mm measured"}
    assert all("Screw thread size not inferred" in t.text for t in selected.data[1:])


def test_coalesced_and_reordered_additions_keep_all_picks():
    a, r = ready()
    i = next(i for i in a.interfaces if i.id == r.interface_id)
    picks = HolePicks()
    event = dict(context=picks.context, interface_id=i.id, hole_ids=i.hole_ids[:2])
    both = add_picked_holes(a, picks, event)
    assert both.hole_ids == i.hole_ids[:2]
    assert add_picked_holes(a, both, click(picks, i)) == both
    assert add_picked_holes(a, both, event) == both
    with pytest.raises(ValueError):
        add_picked_holes(a, both, {**event, "hole_ids": (*i.hole_ids[:2], "invalid")})
    assert both.hole_ids == i.hole_ids[:2]
