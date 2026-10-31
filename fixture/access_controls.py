"""Mouse selection of measured openings and finite access faces."""

from uuid import uuid4
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from .contracts import AccessSelection
from .access import options
from .intake import get_interface
from .face_picking import face_picker_figure
from .face_picker import picker_component
from .planning import patch_requirements


@st.cache_data(max_entries=8, show_spinner=False)
def access_figure(key, _a, _r):
    fig = face_picker_figure(_a)
    for t in fig.data:
        if t.meta and t.meta.get("interface_id"):
            t.meta = {**t.meta, "interface_id": "face:" + t.meta["interface_id"]}
        if t.meta and t.meta.get("direction_for"):
            t.meta = {**t.meta, "direction_for": "face:" + t.meta["direction_for"]}
    i = get_interface(_a, _r.interface_id)
    basis = np.array([i.x, i.y, i.z])
    for id, c in options(_a, _r).items():
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
        fig.add_trace(
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
    return fig.to_json()


@st.fragment
def access_controls(p):
    if not p.requirements.interface_id:
        st.info("Select a mounting face first so access has a defined direction.")
        return
    a, r = p.analysis, p.requirements
    choices = options(a, r)
    key = p.id + str(r.interface_id)
    state = st.session_state.setdefault(
        "access-draft-" + key, {"context": uuid4().hex, "selected": None}
    )
    st.caption(
        "Click a face, opening disk or measured recess. Through openings follow the mounting normal; keep-clear faces create a finite outward box. Selected material/contact conflicts are checked before saving a revision."
    )
    event = picker_component()(
        data=dict(
            figure=access_figure(
                a.source_hash
                + str(a.version)
                + str(r.interface_id)
                + str(r.rear_clearance),
                a,
                r,
            ),
            context=state["context"],
            view_key="access-" + key,
            interface_id=state["selected"],
            hint="Select a face or opening for access. Drag to rotate.",
            selected_hint="Access feature selected. Choose its intent below.",
        ),
        key="access-picker-" + key,
        on_picked_change=lambda: None,
        height=555,
    )
    if (
        event.picked
        and event.picked.get("context") == state["context"]
        and event.picked.get("interface_id") in choices
    ):
        state["selected"] = event.picked["interface_id"]
    ids = [None, *choices]
    selected = st.selectbox(
        "Access feature",
        ids,
        index=ids.index(state["selected"]),
        format_func=lambda v: (
            choices[v]["label"] if v else "Click in 3D or choose here"
        ),
        key="access-feature-" + state["context"] + str(state["selected"]),
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
            p.requirements = patch_requirements(
                r,
                {
                    "access_selections": (
                        *[s for s in r.access_selections if s.feature_id != selected],
                        choice,
                    )
                },
            )
            p.messages.append(
                dict(
                    role="user",
                    content=f"Selected {choices[selected]['label']} for {intent}, padding {padding:g} mm, finite reach {reach:g} mm. Generate a revision to apply it.",
                )
            )
            p.save()
            st.rerun()
        except ValueError as error:
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
                p.requirements = patch_requirements(
                    r,
                    {
                        "access_selections": tuple(
                            s for s in r.access_selections if s.feature_id in retain
                        )
                    },
                )
                p.save()
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    if st.button("Done selecting access"):
        st.session_state.access_mode = False
        st.rerun(scope="app")
