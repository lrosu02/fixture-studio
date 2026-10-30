"""Streamlit component for mouse picking using Plotly's WebGL hit tests."""

from pathlib import Path
import streamlit as st
from plotly.offline import get_plotlyjs
from .picking import HolePicks, add_picked_holes, retain_picked_holes, use_picked_holes
from .planning import missing_questions
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
def picker_geometry(source_hash, _analysis):
    """Serialize the immutable STEP mesh once, not once per picked hole."""
    return hole_picker_figure(_analysis, HolePicks()).to_json()


@st.fragment
def hole_picker_controls(project):
    a, r = project.analysis, project.requirements
    # A fresh source, restored revision or edited requirements invalidates old clicks.
    signature = (project.id, r.interface_id, r.mounting_hole_ids, r.mounting_confirmed)
    if st.session_state.get("hole_pick_signature") != signature:
        holes = r.mounting_hole_ids
        if not holes and r.mounting_confirmed and r.interface_id:
            holes = next(i.hole_ids for i in a.interfaces if i.id == r.interface_id)
        st.session_state.hole_picks = HolePicks(
            interface_id=r.interface_id if holes else None, hole_ids=holes
        )
        st.session_state.hole_pick_signature = signature
        st.session_state.pop("hole_pick_error", None)
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
            "figure": picker_geometry(a.source_hash, a),
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
            picks = add_picked_holes(a, picks, result.picked)
            st.session_state.hole_picks = picks
            st.session_state.pop("hole_pick_error", None)
        except ValueError as error:
            st.session_state.hole_pick_error = str(error)
    if st.session_state.get("hole_pick_error"):
        st.warning(st.session_state.hole_pick_error)
    st.write(
        f"{len(picks.hole_ids)} hole(s) selected"
        + (f" on {picks.interface_id}" if picks.hole_ids else "")
    )
    if picks.hole_ids:
        interface = next(i for i in a.interfaces if i.id == picks.interface_id)
        kept = st.multiselect(
            "Selected holes — remove with ×",
            options=list(picks.hole_ids),
            default=list(picks.hole_ids),
            format_func=lambda h: (
                f"{h} · Ø {interface.diameters[interface.hole_ids.index(h)]:.3f} mm"
            ),
            key="picked-list-" + picks.context + str(picks.hole_ids),
        )
        if tuple(kept) != picks.hole_ids:
            st.session_state.hole_picks = retain_picked_holes(picks, kept)
            st.session_state.pop("hole_pick_error", None)
            st.rerun()
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
    c1, c2 = st.columns(2)
    if c1.button("Clear hole selection"):
        st.session_state.hole_picks = HolePicks()
        st.session_state.pop("hole_pick_error", None)
        st.rerun()
    stationary = st.checkbox(
        "These holes are on the stationary mounting face",
        key="pick-stationary-" + picks.context + str(picks.interface_id),
    )
    if c2.button(
        "Use these mounting holes", disabled=not picks.hole_ids or not stationary
    ):
        try:
            updated = use_picked_holes(a, r, picks, stationary)
            project.requirements = updated
            project.highlights = picks.hole_ids
            project.error = None
            project.stage = (
                "clarifying" if missing_questions(a, updated) else "proposing"
            )
            project.messages.append(
                dict(
                    role="user",
                    content=f"Selected {', '.join(picks.hole_ids)} on {picks.interface_id} in the 3D viewer and confirmed this is the stationary mounting face.",
                )
            )
            project.save()
            st.session_state.close_hole_picker = True
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    if st.button("Cancel hole selection"):
        st.session_state.close_hole_picker = True
        st.rerun()
