"""The interactive model workspace reruns independently of the rest of the app."""

import streamlit as st
from .viewer import assembly_figure
from .display_controls import render_display_controls
from .mounting_picker import render_mounting_picker
from .opening_controls import (
    render_opening_view,
    begin_opening_placement,
    can_place_opening,
    opening_state,
)
from .dimensions import dimension_controls, thickness_controls
from .ui_theme import workspace_intro
from .controls import (
    retention_controls,
    screw_size_controls,
    requirement_controls,
    manufacturing_controls,
    fillet_controls,
    passage_controls,
)
from .base_controls import base_controls
from .hardware_controls import hardware_controls
from .fasteners import resolve_clearances, clearance_summary, SOURCE
from .planning import patch_requirements


BRIDGE_ORIENTATION = (
    "The bridge mounting platform is horizontal, with its mounting normal pointing up. "
    "An L-bracket wall is upright. This changes the mounting orientation and may "
    "conflict with a horizontal shaft requirement."
)


def activate_opening_placement(project, opening_id=None):
    try:
        begin_opening_placement(project, opening_id)
    except ValueError as error:
        opening_state(project)["error"] = str(error)
    else:
        set_workspace_mode("openings", project)


def set_workspace_mode(mode, project):
    st.session_state.face_mode = mode == "face"
    st.session_state.pick_mode = mode == "holes"
    st.session_state.access_mode = mode == "access"
    st.session_state.opening_mode = mode == "openings"
    if mode == "openings":
        for name, value in (
            ("source", False),
            ("fixture", True),
            ("evidence", False),
            ("edit", False),
            ("compare", False),
        ):
            st.session_state[view_key(project, name)] = value


def request_assembly(project, fixture_only=False):
    # A build may finish after these widgets were rendered. Apply the request on
    # the next render, before creating widgets, rather than mutating live keys.
    st.session_state["workspace-view-request"] = (project.id, fixture_only)


def view_key(project, name):
    return f"workspace-view-{project.id}-{name}"


def sync_preview(project):
    revision = (project.id, project.active_id)
    changed = st.session_state.get("workspace-revision") != revision
    st.session_state["workspace-revision"] = revision
    requested = st.session_state.pop("workspace-view-request", None)
    if requested and requested[0] != project.id:
        requested = None
    if requested or (changed and project.current):
        fixture_only = bool(requested and requested[1])
        set_workspace_mode("assembly", project)
        st.session_state[view_key(project, "source")] = not fixture_only
        st.session_state[view_key(project, "fixture")] = True
        st.session_state[view_key(project, "evidence")] = not fixture_only
        st.session_state[view_key(project, "edit")] = False


@st.fragment
def workspace(project, build):
    p = project
    a, r = p.analysis, p.requirements
    if st.session_state.get("workspace-project") != p.id:
        set_workspace_mode("assembly", p)
        st.session_state["workspace-project"] = p.id
    sync_preview(p)
    st.subheader("Model preview")
    workspace_intro()
    if st.session_state.pop("close_hole_picker", False):
        st.session_state.pick_mode = False
    if st.session_state.pop("close_face_picker", False):
        st.session_state.face_mode = False
    selecting = any(
        st.session_state.get(name, False)
        for name in ("face_mode", "pick_mode", "access_mode")
    )
    with st.expander(
        "Choose mounting face and holes",
        expanded=not r.mounting_confirmed or selecting,
    ):
        st.caption(
            "Choose the face that touches the fixture, then select only the holes used "
            "to fasten the part. Picks save immediately."
        )
        face_button, hole_button = st.columns(2)
        for button, label, mode, flag in (
            (face_button, "Select mounting face", "face", "face_mode"),
            (hole_button, "Select mounting holes", "holes", "pick_mode"),
            (st, "Select source access features", "access", "access_mode"),
        ):
            button.button(
                label,
                width="stretch",
                on_click=set_workspace_mode,
                args=(mode, p),
                type="primary" if st.session_state.get(flag) else "secondary",
            )
        st.caption(
            "Source access features reserve space around the uploaded part. "
            "New fixture holes can be placed after the first build."
        )
    face_mode = st.session_state.get("face_mode", False)
    pick_mode = st.session_state.get("pick_mode", False)
    access_mode = st.session_state.get("access_mode", False)
    opening_mode = st.session_state.get("opening_mode", False)
    with st.container(key="fixture-opening-pending-" + p.id):
        pending_openings = [
            opening for opening in r.fixture_openings if opening.needs_placement
        ]
        if p.current and pending_openings:
            st.warning(
                f"{len(pending_openings)} opening(s) need placement. Saved sizes are kept; "
                "choose new positions before including them in the rebuilt fixture."
            )
            if not can_place_opening(p):
                st.caption(
                    "Generate the new fixture type first. The viewer still shows the previous revision."
                )
            st.button(
                "Place next opening",
                key="place-next-opening-" + p.id,
                on_click=activate_opening_placement,
                args=(p, pending_openings[0].id),
                disabled=not can_place_opening(p) or "fixture_openings" in r.locks,
            )
        if p.current and p.current.requirements.composition == "bridge":
            st.info(BRIDGE_ORIENTATION)
        if (
            p.current
            and r.defer_passages
            and r.through_access_required
            and not r.fixture_openings
            and not r.rear_passages
            and not any(
                selection.intent == "through" for selection in r.access_selections
            )
        ):
            st.info(
                "Cable opening not added yet. Use Add a fixture opening to place it."
            )
    selecting = pick_mode or face_mode or access_mode
    if selecting or p.current:
        views = st.columns(2)
        views[0].button(
            "View assembly",
            on_click=request_assembly,
            args=(p,),
            type="primary"
            if not selecting
            and not opening_mode
            and not st.session_state.get(view_key(p, "edit"), False)
            and st.session_state.get(view_key(p, "source"), True)
            and st.session_state.get(view_key(p, "fixture"), True)
            else "secondary",
        )
        if p.current:
            views[1].button(
                "View generated fixture",
                on_click=request_assembly,
                args=(p, True),
                type="primary"
                if not selecting
                and not opening_mode
                and not st.session_state.get(view_key(p, "edit"), False)
                and not st.session_state.get(view_key(p, "source"), True)
                and st.session_state.get(view_key(p, "fixture"), True)
                else "secondary",
            )
        if p.current:
            st.button(
                "Add a fixture opening",
                on_click=activate_opening_placement,
                args=(p,),
                type="primary" if opening_mode else "secondary",
            )
    if selecting and p.current:
        st.caption(
            "Selection view shows the uploaded part. Use View generated fixture to inspect the CAD."
        )
    display = render_display_controls(p, selecting, opening_mode=opening_mode)
    source, fixture, evidence = (display[k] for k in ("source", "fixture", "evidence"))
    dimensions, envelopes = display["dimensions"], display["envelopes"]
    editing_dimensions, compare = display["editing_dimensions"], display["compare"]
    previous = (
        next((v for v in p.revisions if p.current and v.id == p.current.parent), None)
        if compare
        else None
    )
    if selecting:
        render_mounting_picker(
            p,
            "access" if access_mode else "face" if face_mode else "holes",
            on_done=lambda: set_workspace_mode("assembly", p),
        )
    else:
        if editing_dimensions:
            dimension_controls(p, build)
        elif p.current:
            render_opening_view(
                p,
                build,
                enabled=opening_mode,
                source=source,
                fixture=fixture,
                evidence=evidence,
                dimensions=dimensions,
                envelopes=envelopes,
                previous=previous,
                on_done=lambda: set_workspace_mode("assembly", p),
                on_place=lambda opening_id: activate_opening_placement(p, opening_id),
            )
        else:
            st.plotly_chart(
                assembly_figure(
                    a,
                    r.interface_id,
                    p.current,
                    source,
                    fixture,
                    evidence,
                    dimensions,
                    envelopes,
                    previous,
                    highlight_ids=p.highlights
                    or (
                        p.current.requirements.mounting_hole_ids
                        if p.current
                        else r.mounting_hole_ids
                    ),
                ),
                width="stretch",
                config={"displaylogo": False},
            )
    r = p.requirements
    if p.current and not pick_mode:
        with st.expander("Model details", expanded=False):
            c = st.columns(3)
            c[0].metric("Parts held", len(p.current.plan.placements))
            c[1].metric(
                "Fixture volume",
                f"{p.current.metrics['volume_mm3']:,.0f} mm³",
                f"{p.current.metrics['volume_mm3'] - previous.metrics['volume_mm3']:+,.0f} mm³"
                if previous
                else None,
            )
            c[2].metric("Revision", p.current.id[:6])
        if p.current.requirements != r:
            st.info(
                "The viewer shows the last valid revision. Generate to apply edited requirements."
            )
    thickness_controls(p, build)
    mounting, fabrication, advanced = st.tabs(
        ["Mounting", "Fabrication", "Advanced"], key=f"workspace-settings-{p.id}"
    )
    with mounting:
        if r.mounting_confirmed:
            count = len(r.mounting_hole_ids)
            st.caption(
                f"{count} mounting hole{'s' if count != 1 else ''} selected. "
                "Open a section below to change attachment details."
                if count
                else "Mounting face selected. Choose how to support and hold the part below."
            )
        with st.expander(
            "How the part is held", expanded=r.part_attachment == "unselected"
        ):
            if not r.mounting_confirmed:
                st.caption(
                    "Choose a mounting face or holes above to see attachment options."
                )
            retention_controls(p)
            screw_size_controls(p)
            if r.part_attachment == "screws" or r.surroundings == "bolt":
                st.caption(
                    f"Clearance holes use [ISO 273 medium]({SOURCE}) unless overridden."
                )
            if r.interface_id:
                try:
                    clearances = resolve_clearances(a, r)
                    st.caption(clearance_summary(clearances))
                    if any(c.basis.startswith("Assumed") for c in clearances):
                        st.caption(
                            "Screw sizes are suggested from measured openings. Threads are not identified."
                        )
                except ValueError as error:
                    st.warning(str(error))
        hardware_controls(p)
        base_controls(p)
    with fabrication:
        manufacturing_controls(p)
        fillet_controls(p)
    with advanced:
        st.caption(
            "Manual overrides and measured geometry. Most designs can use the controls above."
        )
        mounting_evidence_controls(p)
        passage_controls(p)
        requirement_controls(p)


def mounting_evidence_controls(p):
    a, r = p.analysis, p.requirements
    with st.expander("Advanced — mounting evidence", expanded=False):
        options = [None] + [i.id for i in a.interfaces]
        selected = st.selectbox(
            "Attachment interface",
            options,
            index=options.index(r.interface_id),
            format_func=lambda x: x or "Select a candidate",
        )
        if selected != r.interface_id:
            try:
                p.requirements = patch_requirements(
                    r,
                    dict(
                        interface_id=selected,
                        mounting_hole_ids=(),
                        mounting_confirmed=False,
                        part_attachment="unselected",
                        envelopes=(),
                    ),
                )
                st.rerun()
            except ValueError as error:
                st.error(str(error))
        if selected:
            i = next(i for i in a.interfaces if i.id == selected)
            st.write(i.confidence)
            st.dataframe(
                [
                    dict(feature=h, diameter_mm=d, x_mm=c[0], y_mm=c[1])
                    for h, d, c in zip(i.hole_ids, i.diameters, i.centers)
                ],
                hide_index=True,
            )
            chosen_holes = st.multiselect(
                "Fastener holes (exclude ports or central openings)",
                list(i.hole_ids),
                default=list(r.mounting_hole_ids or i.hole_ids),
                format_func=lambda h: (
                    f"{h} · Ø {i.diameters[i.hole_ids.index(h)]:.3f} mm measured"
                ),
            )
            if st.button("Use selected measured holes"):
                if not chosen_holes:
                    st.error("Select at least one measured hole.")
                else:
                    p.requirements = patch_requirements(
                        r,
                        dict(
                            mounting_hole_ids=tuple(chosen_holes),
                            mounting_confirmed=False,
                            part_attachment="screws",
                        ),
                    )
                    st.rerun()
            st.caption(
                "Outline colors identify measured bore sizes, not screw threads. Frame Z points into the part; fixture Z ≤ 0."
            )
        else:
            st.caption(
                "Select a mounting face above, with or without holes. This list is an optional alternative."
            )
        st.caption(" · ".join(a.limitations))
