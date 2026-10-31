"""Streamlit component for mouse picking using Plotly's WebGL hit tests."""

from pathlib import Path
import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from .picking import HolePicks, add_picked_holes, retain_picked_holes, use_picked_holes
from .face_picking import FacePicks, use_picked_face, face_surface
from .selection_ui import selection_signature, save_selection, rerun_selection
from .viewer import hole_picker_figure, hole_size_colors, hole_size_key


def picker_component():
    return _registered_picker(
        Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    )


@st.cache_resource
def _registered_picker(source):
    return st.components.v2.component(
        "measured_hole_picker",
        html='<div class="hole-picker-plot" style="height:510px;width:100%"></div>'
        '<p class="hole-picker-status" role="status" style="margin:8px 0 0;'
        'font-size:12px;line-height:1.4;white-space:normal;overflow-wrap:anywhere">'
        "Loading 3D hole selection…</p>",
        js=get_plotlyjs() + "\n" + source,
        isolate_styles=False,
    )


@st.cache_data(max_entries=8, show_spinner=False)
def picker_geometry(source_hash, _analysis, face_id=None):
    """Serialize the immutable STEP mesh once, not once per picked hole."""
    figure = hole_picker_figure(_analysis, HolePicks())
    if face_id:
        face = next(i for i in _analysis.interfaces if i.id == face_id)
        points = outer_boundary_points(face_surface(_analysis, face))
        if len(points):
            points = points - np.asarray(face.z) * 0.05
            figure.add_trace(
                go.Scatter3d(
                    x=points[:, 0],
                    y=points[:, 1],
                    z=points[:, 2],
                    mode="lines",
                    line=dict(color="#ffb454", width=6),
                    name="Selected mounting face",
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
    return figure.to_json()


def outer_boundary_points(mesh):
    """Measured outer trim segments; triangle diagonals and bore rims are excluded."""
    if not mesh.triangles:
        return np.empty((0, 3))
    vertices, mapping = np.unique(
        np.asarray(mesh.vertices), axis=0, return_inverse=True
    )
    triangles = mapping[np.asarray(mesh.triangles)]
    edges = np.sort(
        np.concatenate(
            [triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]
        ),
        axis=1,
    )
    edges, counts = np.unique(edges, axis=0, return_counts=True)
    edges = edges[counts == 1]
    adjacent = {}
    for a, b in edges:
        adjacent.setdefault(a, set()).add(b)
        adjacent.setdefault(b, set()).add(a)
    remaining = set(adjacent)
    loops = []
    while remaining:
        pending = [next(iter(remaining))]
        connected = set()
        while pending:
            vertex = pending.pop()
            if vertex in connected:
                continue
            connected.add(vertex)
            pending.extend(adjacent[vertex] - connected)
        remaining -= connected
        loop = [edge for edge in edges if edge[0] in connected]
        loops.append(loop)
    if not loops:
        return np.empty((0, 3))
    outer = max(
        loops,
        key=lambda loop: sum(
            np.linalg.norm(vertices[a] - vertices[b]) for a, b in loop
        ),
    )
    return np.asarray(
        [
            point
            for a, b in outer
            for point in (vertices[a], vertices[b], (np.nan, np.nan, np.nan))
        ]
    )


def begin_hole_selection(project):
    r = project.requirements
    st.session_state.hole_picks = HolePicks(
        interface_id=r.interface_id if r.mounting_hole_ids else None,
        hole_ids=r.mounting_hole_ids,
    )
    st.session_state.hole_pick_signature = selection_signature(project)
    st.session_state.pop("hole_pick_error", None)


def _commit_holes(project, picks):
    r = project.requirements
    if picks.hole_ids:
        updated = use_picked_holes(project.analysis, r, picks, True)
    elif r.mounting_hole_ids:
        updated = use_picked_face(
            project.analysis, r, FacePicks(interface_id=r.interface_id), (), True
        )
    else:
        return False
    changed = save_selection(
        project,
        updated,
        (updated.interface_id, *picks.hole_ids),
        f"3D mounting selection: {', '.join(picks.hole_ids) or 'no part screw holes'} on {picks.interface_id or r.interface_id}.",
    )
    st.session_state.hole_picks = picks
    st.session_state.hole_pick_signature = selection_signature(project)
    return changed


def _replace_holes(project, list_key=None):
    previous = st.session_state.hole_picks
    try:
        kept = st.session_state[list_key] if list_key else ()
        picks = retain_picked_holes(previous, kept)
        _commit_holes(project, picks)
        st.session_state.hole_picks = picks
        st.session_state.pop("hole_pick_error", None)
    except (ValueError, OSError) as error:
        begin_hole_selection(project)
        st.session_state.hole_pick_error = str(error)


@st.fragment
def hole_picker_controls(project):
    render_hole_picker(project)


def render_hole_picker(project):
    a, r = project.analysis, project.requirements
    if st.session_state.get("hole_pick_signature") != selection_signature(project):
        begin_hole_selection(project)
    picks = st.session_state.hole_picks
    # Additions stay in the browser's draft. Only explicit removal/reset changes
    # this seed, keeping component data identical across click-triggered reruns.
    seed_key = "hole-picker-seed-" + project.id
    seed = st.session_state.get(seed_key)
    if seed is None or seed.context != picks.context:
        seed = picks
        st.session_state[seed_key] = seed
    if not a.interfaces:
        st.info(
            "No supported circular holes were detected on planar faces. There are no measured holes to pick."
        )
        return
    st.caption(
        "Click a large colored center or rim to add a hole. Clicking again keeps it selected. Drag to rotate. Remove holes using × in the selected-hole list below. After the first pick, only that face's selectors remain visible."
    )
    # Only numeric diameter labels and internally generated CSS colors enter HTML.
    legend = "".join(
        '<span role="listitem" style="display:inline-flex;align-items:center;gap:6px;'
        'border:1px solid #718095;border-radius:6px;padding:4px 8px">'
        f'<span aria-hidden="true" style="color:{color};font-size:20px">●</span>'
        f"Ø {size} mm</span>"
        for size, color in hole_size_colors(a).items()
    )
    st.markdown(
        '<div role="list" aria-label="Measured hole diameters" '
        f'style="display:flex;flex-wrap:wrap;gap:8px">{legend}</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Measured bore diameters from STEP, displayed to 0.001 mm. Colors do not identify screw threads. Fixture clearances default to ISO 273; inferred metric screw sizes are recorded as assumptions."
    )
    result = picker_component()(
        data={
            "figure": picker_geometry(
                a.source_hash, a, r.interface_id if r.mounting_confirmed else None
            ),
            "context": seed.context,
            "view_key": project.id,
            "interface_id": seed.interface_id,
            "hole_ids": list(seed.hole_ids),
        },
        key="hole-picker-" + project.id,
        on_picked_change=lambda: None,
        height=555,
    )
    if result.picked:
        try:
            chosen = add_picked_holes(a, picks, result.picked)
            _commit_holes(project, chosen)
            picks = st.session_state.hole_picks = chosen
            st.session_state.pop("hole_pick_error", None)
        except (ValueError, OSError) as error:
            if result.picked.get("context") == picks.context:
                begin_hole_selection(project)
                st.session_state.hole_pick_error = str(error)
                rerun_selection()
            st.session_state.hole_pick_error = str(error)
    if st.session_state.get("hole_pick_error"):
        st.warning(st.session_state.hole_pick_error)
    st.write(
        f"{len(picks.hole_ids)} hole(s) selected"
        + (f" on {picks.interface_id}" if picks.hole_ids else "")
    )
    if picks.hole_ids:
        interface = next(i for i in a.interfaces if i.id == picks.interface_id)
        list_key = "picked-list-" + picks.context + str(picks.hole_ids)
        st.multiselect(
            "Selected holes — remove with ×",
            options=list(picks.hole_ids),
            default=list(picks.hole_ids),
            format_func=lambda h: (
                f"{h} · Ø {interface.diameters[interface.hole_ids.index(h)]:.3f} mm"
            ),
            key=list_key,
            on_change=_replace_holes,
            args=(project, list_key),
        )
        st.caption(
            " · ".join(
                f"{h}: {d:.3f} mm measured bore"
                for h, d in zip(interface.hole_ids, interface.diameters)
                if h in picks.hole_ids
            )
        )
        sizes = {
            hole_size_key(d)
            for h, d in zip(interface.hole_ids, interface.diameters)
            if h in picks.hole_ids
        }
        if len(sizes) > 1:
            st.info(
                "Different measured hole sizes are selected. Automatic clearance is resolved separately for each hole. A specified nominal screw size or custom diameter applies to the whole selected pattern."
            )
    st.button(
        "Clear hole selection",
        on_click=_replace_holes,
        args=(project,),
        disabled=not picks.hole_ids,
    )
    st.caption(
        "Choices save immediately. Existing CAD changes only when you generate a revision."
    )
