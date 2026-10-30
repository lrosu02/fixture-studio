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
from .planning import missing_questions


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
def picker_geometry(source_hash, _analysis):
    figure = face_picker_figure(_analysis)
    return figure.to_json()


@st.fragment
def face_picker_controls(project):
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
    signature = (
        project.id,
        r.interface_id,
        r.mounting_hole_ids,
        r.mounting_confirmed,
        r.part_attachment,
    )
    if st.session_state.get("face_pick_signature") != signature:
        st.session_state.face_picks = FacePicks(interface_id=r.interface_id)
        st.session_state.face_pick_signature = signature
        st.session_state.pop("face_pick_error", None)
    picks = st.session_state.face_picks
    st.caption(
        "Click the flat surface that should contact the fixture. Drag to rotate; clicking again keeps it selected. Orange shows the selected face and the side where the fixture will sit."
    )
    result = picker_component()(
        data=dict(
            figure=picker_geometry(a.source_hash + ":" + str(a.version), a),
            context=picks.context,
            view_key=project.id,
            interface_id=picks.interface_id,
        ),
        key="face-picker-" + project.id,
        on_picked_change=lambda: None,
        height=555,
    )
    if result.picked:
        try:
            picks = pick_face(a, picks, result.picked)
            st.session_state.face_picks = picks
            st.session_state.pop("face_pick_error", None)
        except ValueError as error:
            st.session_state.face_pick_error = str(error)
    if st.session_state.get("face_pick_error"):
        st.warning(st.session_state.face_pick_error)
    options = [None, *(i.id for i in a.interfaces)]
    labels = {i.id: face_label(i) for i in a.interfaces}
    selected = st.selectbox(
        "Mounting face",
        options,
        index=options.index(picks.interface_id),
        format_func=lambda v: labels.get(v, "Click a face or choose here"),
        key="face-list-" + picks.context + str(picks.interface_id),
    )
    if selected != picks.interface_id:
        st.session_state.face_picks = FacePicks(interface_id=selected)
        st.rerun()
    if picks.interface_id:
        interface = next(i for i in a.interfaces if i.id == picks.interface_id)
        same = r.interface_id == interface.id and r.mounting_confirmed
        holes = st.multiselect(
            "Mounting holes on this face",
            list(interface.hole_ids),
            default=list(
                (r.mounting_hole_ids or interface.hole_ids)
                if r.part_attachment == "screws"
                else ()
            )
            if same
            else list(interface.hole_ids),
            format_func=lambda h: (
                f"{h} · Ø{interface.diameters[interface.hole_ids.index(h)]:.3f} mm"
            ),
            key="face-holes-" + picks.context + interface.id,
        )
        valid = all(interface.contact_valid[interface.hole_ids.index(h)] for h in holes)
        if not holes:
            st.info(
                "This face can support a fixture without screw holes. Choose how the part will be retained after applying the face."
            )
        if not valid:
            st.warning(
                "Some selected holes lack enough measured contact area on this side. Review the opposite flange face or remove those holes."
            )
        if r.interface_id != interface.id and (r.rear_passages or r.envelopes):
            st.caption(
                "Changing faces clears old face-relative passage choices and access boxes. Their positions must be reviewed in the new frame."
            )
        confirmed = st.checkbox(
            "This is the mounting surface and the selected holes are for fasteners"
            if holes
            else "This is the surface that should contact the fixture",
            value=same,
            key="face-confirm-" + picks.context + interface.id,
        )
        if st.button("Use this mounting face", disabled=not confirmed):
            try:
                updated = use_picked_face(a, r, picks, holes, confirmed)
                project.requirements = updated
                project.highlights = (interface.id,)
                project.error = None
                project.stage = (
                    "clarifying" if missing_questions(a, updated) else "proposing"
                )
                project.messages.append(
                    dict(
                        role="user",
                        content=f"Selected {face_label(interface)} ({interface.id}) as the mounting surface in the 3D viewer. "
                        + (
                            f"Confirmed holes {', '.join(holes)} as fasteners. "
                            if holes
                            else "Use this surface without part screw holes; discuss retention. "
                        )
                        + "The fixture belongs on the indicated outside of this face.",
                    )
                )
                project.save()
                st.session_state.close_face_picker = True
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    if st.button("Cancel face selection"):
        st.session_state.close_face_picker = True
        st.rerun()
