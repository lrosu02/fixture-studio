"""One persistent viewer and ordered, immediately saved mounting selections."""

from hashlib import sha256
from pathlib import Path

import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from pydantic import Field

from .contracts import Record
from .face_picking import (
    FacePicks,
    face_label,
    face_picker_figure,
    face_surface,
    use_picked_face,
)
from .hole_picker import outer_boundary_points
from .picking import HolePicks
from .selection_ui import save_selection, selection_signature
from .viewer import hole_picker_figure, hole_size_colors


class MountingEvent(Record):
    context: str
    sequence: int = Field(ge=1)
    interface_id: str
    hole_ids: tuple[str, ...] = Field(default=(), max_length=1024)


@st.cache_resource
def _registered(source):
    return st.components.v2.component(
        "mounting_picker_" + sha256(source.encode()).hexdigest()[:10],
        html='<div class="mounting-picker-plot" style="height:510px;width:100%"></div>'
        '<p class="mounting-picker-status" role="status" style="font-size:12px">'
        "Loading mounting selection…</p>",
        js=get_plotlyjs() + "\n" + source,
        isolate_styles=False,
    )


def picker_component():
    directory = Path(__file__).parent
    # Share the same measured-surface ray tests as the access/base picker.
    helpers = (
        (directory / "face_picker.js")
        .read_text(encoding="utf-8")
        .partition("export default function")[0]
    )
    return _registered(
        helpers + (directory / "mounting_picker.js").read_text(encoding="utf-8")
    )


@st.cache_data(max_entries=8, show_spinner=False)
def picker_geometry(source_key, _analysis):
    figure = face_picker_figure(_analysis)
    holes = hole_picker_figure(_analysis, HolePicks())
    figure.add_traces(list(holes.data[1:]))
    for interface in _analysis.interfaces:
        points = outer_boundary_points(face_surface(_analysis, interface))
        if not len(points):
            continue
        points = points - np.asarray(interface.z) * 0.05
        figure.add_trace(
            go.Scatter3d(
                x=points[:, 0],
                y=points[:, 1],
                z=points[:, 2],
                mode="lines",
                line=dict(color="#ffb454", width=6),
                name="Selected mounting face",
                meta=dict(outline_for=interface.id),
                hoverinfo="skip",
                showlegend=False,
                visible=False,
            )
        )
    vertices = np.asarray(_analysis.mesh.vertices)
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    padding = max(high - low) * 0.25
    spans = high - low + padding * 2
    figure.update_layout(
        scene=dict(
            aspectmode="manual",
            aspectratio=dict(zip("xyz", (spans / np.cbrt(np.prod(spans))).tolist())),
        )
    )
    figure.update_layout(
        scene={
            axis + "axis": dict(
                range=[float(low[n] - padding), float(high[n] + padding)],
                autorange=False,
            )
            for n, axis in enumerate("xyz")
        }
    )
    return figure.to_json()


def reset_selection(project):
    r = project.requirements
    st.session_state.mounting_picks = HolePicks(
        interface_id=r.interface_id if r.mounting_confirmed else None,
        hole_ids=r.mounting_hole_ids,
    )
    st.session_state.mounting_pick_signature = selection_signature(project)
    st.session_state.mounting_pick_sequence = 0


def sync_selection(project):
    if st.session_state.get("mounting_pick_signature") != selection_signature(project):
        reset_selection(project)
        st.session_state.pop("mounting_pick_error", None)


def apply_event(project, event):
    if not event:
        return
    sync_selection(project)
    picks = st.session_state.mounting_picks
    # Explicit removals, external edits and project changes invalidate old events.
    if event.get("context") != picks.context:
        return
    try:
        click = MountingEvent.model_validate(event)
        if click.sequence <= st.session_state.mounting_pick_sequence:
            return
        updated = use_picked_face(
            project.analysis,
            project.requirements,
            FacePicks(interface_id=click.interface_id),
            click.hole_ids,
            True,
        )
        save_selection(
            project,
            updated,
            (click.interface_id, *click.hole_ids),
            f"3D mounting selection: face {click.interface_id}; explicit screw holes: "
            + (", ".join(click.hole_ids) or "none")
            + ".",
        )
        st.session_state.mounting_picks = picks.model_copy(
            update={"interface_id": click.interface_id, "hole_ids": click.hole_ids}
        )
        st.session_state.mounting_pick_signature = selection_signature(project)
        st.session_state.mounting_pick_sequence = click.sequence
        st.session_state.pop("mounting_pick_error", None)
    except (ValueError, OSError) as error:
        reset_selection(project)
        st.session_state.mounting_pick_error = str(error)


def _on_pick(project, key):
    apply_event(project, st.session_state.get(key, {}).get("picked"))


def _replace(project, key=None, face=False):
    sync_selection(project)
    picks = st.session_state.mounting_picks
    interface_id = st.session_state[key] if face else picks.interface_id
    holes = (
        picks.hole_ids
        if face and interface_id == picks.interface_id
        else ()
        if face or key is None
        else tuple(st.session_state[key])
    )
    apply_event(
        project,
        dict(
            context=picks.context,
            sequence=st.session_state.mounting_pick_sequence + 1,
            interface_id=interface_id,
            hole_ids=holes,
        ),
    )
    reset_selection(project)


def render_mounting_picker(project, mode, on_done=None):
    a = project.analysis
    if not a.interfaces:
        st.info("No supported mounting surfaces were detected in this STEP.")
        return
    sync_selection(project)
    picks = st.session_state.mounting_picks
    key = "mounting-picker-" + project.id
    source_key = f"{project.id}:{a.source_hash}:{a.version}"
    transport = st.session_state.get(key, {})
    request = transport.get("geometry_request")
    send_geometry = bool(request and request != transport.get("geometry_loaded"))
    from .access_controls import (
        access_state,
        access_pick_geometry,
        apply_access_event,
        render_access_controls,
    )

    access_data = {}
    if mode == "access":
        access_key, access, access_choices = access_state(project)
        access_token = str(request) + ":" + access_key
        access_data = dict(
            access_context=access["context"],
            access_sequence=access["sequence"],
            access_selected=access["selected"],
            access_ids=list(access_choices),
            access_token=access_token,
            access_geometry=access_pick_geometry(access_key, a, project.requirements)
            if request
            and access_choices
            and transport.get("access_geometry_loaded") != access_token
            else None,
        )
    result = picker_component()(
        data=dict(
            # The browser requests immutable geometry once per actual mount.
            # Subsequent picks carry only IDs; never resend megabytes per click.
            figure=picker_geometry(source_key, a) if send_geometry else None,
            geometry_token=request if send_geometry else None,
            source_key=source_key,
            mode=mode,
            context=picks.context,
            sequence=st.session_state.mounting_pick_sequence,
            interface_id=picks.interface_id,
            hole_ids=list(picks.hole_ids),
            **access_data,
        ),
        key=key,
        on_picked_change=lambda: _on_pick(project, key),
        on_geometry_request_change=lambda: None,
        on_geometry_loaded_change=lambda: None,
        on_access_geometry_loaded_change=lambda: None,
        on_access_picked_change=lambda: apply_access_event(
            project, st.session_state.get(key, {}).get("access_picked")
        ),
        height=555,
    )
    # Also supports direct rendering and AppTest; already acknowledged events are no-ops.
    apply_event(project, result.picked)
    apply_access_event(project, getattr(result, "access_picked", None))
    if mode == "access":
        render_access_controls(project, on_done=on_done, viewer=False)
        return
    picks = st.session_state.mounting_picks
    if st.session_state.get("mounting_pick_error"):
        st.warning(st.session_state.mounting_pick_error)
    if mode == "holes":
        st.caption(
            "Click a colored center or rim to add a hole. Repeat clicks keep it selected. "
            "Drag to rotate. Remove holes with × below."
        )
        legend = "".join(
            f'<span style="margin-right:16px"><span style="color:{color}">●</span> '
            f"Ø {size} mm</span>"
            for size, color in hole_size_colors(a).items()
        )
        st.markdown(legend, unsafe_allow_html=True)
        st.write(f"{len(picks.hole_ids)} hole(s) selected")
    else:
        st.caption(
            "Click the surface that should contact the fixture. Orange marks the selected "
            "face; selected holes stay visible. Drag to rotate."
        )
        options = ([None] if picks.interface_id is None else []) + [
            i.id for i in a.interfaces
        ]
        labels = {i.id: face_label(i) for i in a.interfaces}
        face_key = f"mounting-face-list-{picks.context}-{picks.interface_id}"
        st.selectbox(
            "Mounting face",
            options,
            index=options.index(picks.interface_id),
            format_func=lambda v: labels.get(v, "Click a face or choose here"),
            key=face_key,
            on_change=_replace,
            args=(project, face_key, True),
        )
    if picks.interface_id:
        interface = next(i for i in a.interfaces if i.id == picks.interface_id)
        holes_key = f"mounting-hole-list-{mode}-{picks.context}-{picks.hole_ids}"
        if picks.hole_ids or mode == "face":
            st.multiselect(
                "Selected holes — remove with ×"
                if mode == "holes"
                else "Mounting holes on this face",
                list(picks.hole_ids if mode == "holes" else interface.hole_ids),
                default=list(picks.hole_ids),
                format_func=lambda h: (
                    f"{h} · Ø{interface.diameters[interface.hole_ids.index(h)]:.3f} mm"
                ),
                key=holes_key,
                on_change=_replace,
                args=(project, holes_key),
            )
        if mode == "face" and not picks.hole_ids:
            st.info(
                "Face selected without screw holes. Select individual mounting holes if needed."
            )
    if mode == "holes":
        st.button(
            "Clear hole selection",
            on_click=_replace,
            args=(project,),
            disabled=not picks.hole_ids,
        )
        st.caption(
            "Colors show measured bore sizes, not screw threads. Fixture clearances default to ISO 273."
        )
        if (
            picks.hole_ids
            and len(
                {
                    round(interface.diameters[interface.hole_ids.index(h)], 3)
                    for h in picks.hole_ids
                }
            )
            > 1
        ):
            st.info(
                "Different measured hole sizes are selected. Automatic clearance is resolved separately for each hole."
            )
    st.caption("Choices save immediately. Generate a revision to change CAD.")
