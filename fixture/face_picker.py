"""Fast face-selection UI, separate from native geometry work."""

from pathlib import Path
from hashlib import sha256
import streamlit as st
from plotly.offline import get_plotlyjs
from .face_picking import (
    FacePicks,
    pick_face,
    use_picked_face,
    face_picker_figure,
    face_label,
)
from .selection_ui import selection_signature, save_selection, rerun_selection
from .picking import HolePicks
from .viewer import hole_picker_figure


@st.cache_resource
def _registered(source):
    return st.components.v2.component(
        "measured_face_picker_" + sha256(source.encode()).hexdigest()[:10],
        html='<div class="face-picker-plot" style="height:510px;width:100%"></div><p class="face-picker-status" role="status" style="font-size:12px">Loading mounting faces…</p>',
        js=get_plotlyjs() + "\n" + source,
        isolate_styles=False,
    )


def picker_component():
    return _registered(Path(__file__).with_suffix(".js").read_text(encoding="utf-8"))


@st.cache_data(max_entries=8, show_spinner=False)
def picker_geometry(source_hash, _analysis, hole_ids=()):
    figure = face_picker_figure(_analysis)
    if hole_ids:
        selected_face = next(
            i.id for i in _analysis.interfaces if set(hole_ids) <= set(i.hole_ids)
        )
        holes = hole_picker_figure(
            _analysis, HolePicks(interface_id=selected_face, hole_ids=hole_ids)
        )
        for trace in holes.data:
            if trace.meta and trace.meta.get("hole_id") in hole_ids:
                figure.add_trace(trace)
    return figure.to_json()


def begin_face_selection(project):
    r = project.requirements
    st.session_state.face_picks = FacePicks(
        interface_id=r.interface_id if r.mounting_confirmed else None
    )
    st.session_state.face_pick_signature = selection_signature(project)
    st.session_state.pop("face_pick_error", None)


def _commit_face(project, picks, holes=None):
    r = project.requirements
    if holes is None:
        holes = r.mounting_hole_ids if picks.interface_id == r.interface_id else ()
    updated = use_picked_face(project.analysis, r, picks, tuple(holes), True)
    changed = save_selection(
        project,
        updated,
        (picks.interface_id, *holes),
        f"3D mounting selection: face {picks.interface_id}; explicit screw holes: {', '.join(holes) or 'none'}.",
    )
    st.session_state.face_picks = picks
    st.session_state.face_pick_signature = selection_signature(project)
    return changed


def _choose_from_list(project, key, holes=False):
    try:
        picks = st.session_state.face_picks
        if holes:
            _commit_face(project, picks, st.session_state[key])
        else:
            _commit_face(project, FacePicks(interface_id=st.session_state[key]))
        st.session_state.pop("face_pick_error", None)
    except (ValueError, OSError) as error:
        begin_face_selection(project)
        st.session_state.face_pick_error = str(error)


@st.fragment
def face_picker_controls(project):
    render_face_picker(project)


def render_face_picker(project):
    a, r = project.analysis, project.requirements
    if a.version == 1:
        st.info(
            "This saved analysis contains only the older mounting candidates. Re-upload the original STEP to select additional faces without holes; existing revisions remain saved."
        )
    if not a.interfaces:
        st.info(
            "No planar support faces were found. Curved-face-only mounting is not supported yet."
        )
        return
    if st.session_state.get("face_pick_signature") != selection_signature(project):
        begin_face_selection(project)
    picks = st.session_state.face_picks
    st.caption(
        "Click the flat surface that should contact the fixture. Drag to rotate; clicking again keeps it selected. Choices save immediately. Orange shows the selected face and fixture side; selected holes remain marked."
    )
    result = picker_component()(
        data=dict(
            figure=picker_geometry(
                a.source_hash + ":" + str(a.version), a, r.mounting_hole_ids
            ),
            context=picks.context,
            view_key=project.id,
            interface_id=picks.interface_id,
            selected_hint="Mounting face saved. Drag to rotate or choose another feature.",
        ),
        key="face-picker-" + project.id,
        on_picked_change=lambda: None,
        height=555,
    )
    if result.picked:
        try:
            chosen = pick_face(a, picks, result.picked)
            changed = _commit_face(project, chosen)
            st.session_state.pop("face_pick_error", None)
            if changed:
                rerun_selection()
            picks = chosen
        except (ValueError, OSError) as error:
            if result.picked.get("context") == picks.context:
                begin_face_selection(project)
                st.session_state.face_pick_error = str(error)
                rerun_selection()
            st.session_state.face_pick_error = str(error)
    if st.session_state.get("face_pick_error"):
        st.warning(st.session_state.face_pick_error)
    options = ([None] if picks.interface_id is None else []) + [
        i.id for i in a.interfaces
    ]
    labels = {i.id: face_label(i) for i in a.interfaces}
    face_key = "face-list-" + picks.context + str(picks.interface_id)
    st.selectbox(
        "Mounting face",
        options,
        index=options.index(picks.interface_id),
        format_func=lambda v: labels.get(v, "Click a face or choose here"),
        key=face_key,
        on_change=_choose_from_list,
        args=(project, face_key),
    )
    if picks.interface_id:
        interface = next(i for i in a.interfaces if i.id == picks.interface_id)
        hole_key = (
            "face-holes-" + picks.context + interface.id + str(r.mounting_hole_ids)
        )
        st.multiselect(
            "Mounting holes on this face",
            list(interface.hole_ids),
            default=list(r.mounting_hole_ids) if r.interface_id == interface.id else [],
            format_func=lambda h: (
                f"{h} · Ø{interface.diameters[interface.hole_ids.index(h)]:.3f} mm"
            ),
            key=hole_key,
            on_change=_choose_from_list,
            args=(project, hole_key, True),
        )
        if not r.mounting_hole_ids:
            st.info(
                "Face selected without screw holes. Click individual holes in Select mounting holes, or choose them in the list."
            )
    st.caption(
        "Selections save immediately. Choosing another face clears incompatible holes. Generate a revision to change CAD."
    )
