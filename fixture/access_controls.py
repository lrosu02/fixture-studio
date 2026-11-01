"""Mouse selection of measured openings and finite access faces."""

from uuid import uuid4
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from .contracts import AccessSelection
from .access import options
from .intake import get_interface
from .face_picking import face_picker_figure, face_surface
from .hole_picker import outer_boundary_points
from .picking import HolePicks
from .viewer import hole_picker_figure
from .planning import patch_requirements
from .selection_ui import save_selection, rerun_selection


@st.cache_data(max_entries=8, show_spinner=False)
def access_figure(key, _a, _r):
    fig = face_picker_figure(_a)
    for t in fig.data:
        if t.meta and t.meta.get("interface_id"):
            t.meta = {**t.meta, "interface_id": "face:" + t.meta["interface_id"]}
        if t.meta and t.meta.get("direction_for"):
            t.meta = {**t.meta, "direction_for": "face:" + t.meta["direction_for"]}
    i = get_interface(_a, _r.interface_id)
    if _r.mounting_confirmed:
        outline = outer_boundary_points(face_surface(_a, i))
        if len(outline):
            outline = outline - np.asarray(i.z) * 0.05
            fig.add_trace(
                go.Scatter3d(
                    x=outline[:, 0],
                    y=outline[:, 1],
                    z=outline[:, 2],
                    mode="lines",
                    line=dict(color="#ffb454", width=6),
                    name="Selected mounting face",
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
    if _r.mounting_hole_ids:
        holes = hole_picker_figure(
            _a, HolePicks(interface_id=i.id, hole_ids=_r.mounting_hole_ids)
        )
        for trace in holes.data:
            if trace.meta and trace.meta.get("hole_id") in _r.mounting_hole_ids:
                fig.add_trace(trace)
    fig.add_traces(access_disks(_a, _r))
    return fig.to_json()


def access_disks(a, r):
    i = get_interface(a, r.interface_id)
    basis = np.array([i.x, i.y, i.z])
    traces = []
    for id, c in options(a, r).items():
        if c["kind"] == "face":
            continue
        if c["kind"] == "hole":
            # Only parallel apertures can be represented by this mounting-frame disk.
            if abs(c["outward"][2]) < 0.999:
                continue
            theta = np.linspace(0, 2 * np.pi, 33)
            p = np.column_stack(
                [
                    c["center"][0] + c["diameter"] / 2 * np.cos(theta),
                    c["center"][1] + c["diameter"] / 2 * np.sin(theta),
                    np.full(33, c["center"][2]),
                ]
            )
        else:
            op = c["region"]
            x, y, z = op.origin
            dx, dy, _ = op.size
            if op.shape == "cylinder":
                theta = np.linspace(0, 2 * np.pi, 33)
                p = np.column_stack(
                    [
                        x + dx / 2 * np.cos(theta),
                        y + dy / 2 * np.sin(theta),
                        np.full(33, z - 0.05),
                    ]
                )
            elif op.shape == "prism":
                p = np.array([(x + u, y + v, z - 0.05) for u, v in op.profile])
            else:
                p = np.array(
                    [
                        (x, y, z - 0.05),
                        (x + dx, y, z - 0.05),
                        (x + dx, y + dy, z - 0.05),
                        (x, y + dy, z - 0.05),
                    ]
                )
        p = p @ basis + np.array(i.origin)
        n = len(p)
        traces.append(
            go.Mesh3d(
                x=p[:, 0],
                y=p[:, 1],
                z=p[:, 2],
                i=[0] * (n - 2),
                j=list(range(1, n - 1)),
                k=list(range(2, n)),
                color="#74a9bc",
                flatshading=True,
                hoverinfo="skip",
                meta={"pick_kind": "face", "interface_id": id},
                name=c["label"],
            )
        )
    return traces


@st.fragment
def access_controls(p):
    render_access_controls(p)


def _finish_access():
    st.session_state.access_mode = False
    rerun_selection()


@st.cache_data(max_entries=12, show_spinner=False)
def access_catalog(key, _a, _r):
    return options(_a, _r)


def access_state(p):
    r = p.requirements
    key = f"{p.id}:{r.interface_id}:{r.rear_clearance}"
    state = st.session_state.setdefault(
        "access-draft-" + key, {"context": uuid4().hex, "selected": None, "sequence": 0}
    )
    choices = access_catalog(key, p.analysis, r) if r.interface_id else {}
    return key, state, choices


def apply_access_event(p, event):
    if not isinstance(event, dict):
        return
    _, state, choices = access_state(p)
    if event.get("context") != state["context"]:
        return
    sequence = event.get("sequence")
    if type(sequence) is not int or sequence <= state["sequence"]:
        return
    if event.get("feature_id") not in choices:
        return
    state.update(selected=event["feature_id"], sequence=sequence)


@st.cache_data(max_entries=12, show_spinner=False)
def access_pick_geometry(key, _a, _r):
    # Source and face triangles already live in the persistent viewer. Send only
    # opening/recess disks when the mounting frame changes, not a second scene.
    from plotly.io import to_json

    import json

    return json.dumps(json.loads(to_json(go.Figure(access_disks(_a, _r))))["data"])


def render_access_controls(p, on_done=None, viewer=True):
    if viewer:
        from .mounting_picker import render_mounting_picker

        return render_mounting_picker(p, "access", on_done=on_done)
    if not p.requirements.interface_id:
        st.info("Select a mounting face first so access has a defined direction.")
        return
    r = p.requirements
    key, state, choices = access_state(p)
    st.caption(
        "Click a face, opening disk or measured recess. Through openings follow the mounting normal; keep-clear faces create a finite outward box. Selected material/contact conflicts are checked before saving a revision."
    )
    st.caption(
        "Your mounting face outline and selected screw-hole markers remain visible."
    )
    ids = [None, *choices]
    selected = st.selectbox(
        "Access feature",
        ids,
        index=ids.index(state["selected"]),
        format_func=lambda v: (
            choices[v]["label"] if v else "Click in 3D or choose here"
        ),
        key="access-feature-" + state["context"] + str(state["selected"]),
        on_change=_choose_access,
        args=(p, "access-feature-" + state["context"] + str(state["selected"])),
    )
    intent = st.radio(
        "Access intent",
        ["through", "keep_clear"],
        format_func=lambda v: "Through opening" if v == "through" else "Keep clear",
        horizontal=True,
    )
    padding = st.number_input("Access padding (mm)", 0.3, 20.0, 0.5, step=0.1)
    reach = st.number_input(
        "Outward access distance (mm)", 0.1, 500.0, 10.0, disabled=intent == "through"
    )
    if st.button("Add selected access", disabled=selected is None):
        try:
            choice = AccessSelection(
                feature_id=selected, intent=intent, padding=padding, reach=reach
            )
            updated = patch_requirements(
                r,
                {
                    "access_selections": (
                        *[s for s in r.access_selections if s.feature_id != selected],
                        choice,
                    )
                },
            )
            save_selection(
                p,
                updated,
                p.highlights,
                f"Selected {choices[selected]['label']} for {intent}, padding {padding:g} mm, finite reach {reach:g} mm. Generate a revision to apply it.",
            )
            rerun_selection()
        except (ValueError, OSError) as error:
            st.error(str(error))
    if r.access_selections:
        retain = st.multiselect(
            "Saved access selections",
            [s.feature_id for s in r.access_selections],
            default=[s.feature_id for s in r.access_selections],
            format_func=lambda v: choices.get(v, {}).get("label", v),
            key="access-retained-" + key + str(hash(r.model_dump_json())),
        )
        if st.button("Save access selection list"):
            try:
                updated = patch_requirements(
                    r,
                    {
                        "access_selections": tuple(
                            s for s in r.access_selections if s.feature_id in retain
                        )
                    },
                )
                save_selection(
                    p, updated, p.highlights, "Updated saved access selections."
                )
                rerun_selection()
            except (ValueError, OSError) as error:
                st.error(str(error))
    st.button("Done selecting access", on_click=on_done or _finish_access)


def _choose_access(p, key):
    _, state, _ = access_state(p)
    state.update(selected=st.session_state[key], sequence=0, context=uuid4().hex)
