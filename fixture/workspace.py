"""The interactive model workspace reruns independently of the rest of the app."""

import streamlit as st
from .viewer import assembly_figure
from .hole_picker import render_hole_picker, begin_hole_selection
from .face_picker import render_face_picker, begin_face_selection
from .access_controls import render_access_controls
from .dimensions import dimension_controls, thickness_controls
from .ui_theme import workspace_intro
from .controls import (
    retention_controls,
    screw_size_controls,
    requirement_controls,
    manufacturing_controls,
    passage_controls,
)
from .base_controls import base_controls
from .hardware_controls import hardware_controls
from .fasteners import resolve_clearances, clearance_summary, SOURCE
from .planning import patch_requirements


def set_workspace_mode(mode, project):
    st.session_state.face_mode = mode == "face"
    st.session_state.pick_mode = mode == "holes"
    st.session_state.access_mode = mode == "access"
    if mode == "face":
        begin_face_selection(project)
    elif mode == "holes":
        begin_hole_selection(project)


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
    st.subheader("Design choices")
    workspace_intro()
    if st.session_state.pop("close_hole_picker", False):
        st.session_state.pick_mode = False
    if st.session_state.pop("close_face_picker", False):
        st.session_state.face_mode = False
    face_button, hole_button = st.columns(2)
    if face_button.button("Select mounting face", width="stretch"):
        set_workspace_mode("face", p)
    if hole_button.button("Select mounting holes", width="stretch"):
        set_workspace_mode("holes", p)
    if st.button("Select openings / keep-clear areas", width="stretch"):
        set_workspace_mode("access", p)
    face_mode = st.session_state.get("face_mode", False)
    pick_mode = st.session_state.get("pick_mode", False)
    access_mode = st.session_state.get("access_mode", False)
    selecting = pick_mode or face_mode or access_mode
    if selecting or p.current:
        views = st.columns(2)
        views[0].button("View assembly", on_click=request_assembly, args=(p,))
        if p.current:
            views[1].button(
                "View generated fixture", on_click=request_assembly, args=(p, True)
            )
    if selecting and p.current:
        st.caption(
            "Selection view shows the uploaded part. Use View generated fixture to inspect the CAD."
        )
    with st.expander("View options", expanded=False):
        toggles = st.columns(5)
        for name, default in (("source", True), ("fixture", True), ("evidence", True)):
            st.session_state.setdefault(view_key(p, name), default)
        source = toggles[0].checkbox(
            "Source", key=view_key(p, "source"), disabled=selecting
        )
        fixture = toggles[1].checkbox(
            "Fixture", key=view_key(p, "fixture"), disabled=selecting
        )
        evidence = toggles[2].checkbox(
            "Mounting holes", key=view_key(p, "evidence"), disabled=selecting
        )
        dimensions = toggles[3].checkbox("Dimensions", False, disabled=selecting)
        envelopes = toggles[4].checkbox("Access volumes", False, disabled=selecting)
        compare = st.checkbox(
            "Overlay previous revision",
            False,
            disabled=selecting or not (p.current and p.current.parent),
        )
    previous = (
        next((v for v in p.revisions if p.current and v.id == p.current.parent), None)
        if compare
        else None
    )
    if access_mode:
        render_access_controls(p, on_done=lambda: set_workspace_mode("assembly", p))
    elif face_mode:
        render_face_picker(p)
    elif pick_mode:
        render_hole_picker(p)
    else:
        st.session_state.setdefault(view_key(p, "edit"), False)
        editing_dimensions = st.checkbox(
            "Edit dimensions on model",
            key=view_key(p, "edit"),
            disabled=p.current is None,
        )
        if editing_dimensions:
            dimension_controls(p, build)
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
        c = st.columns(3)
        c[0].metric("Source instances", len(p.current.plan.placements))
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
    retention_controls(p)
    screw_size_controls(p)

    if r.part_attachment == "screws" or r.surroundings == "bolt":
        st.caption(
            f"Clearance holes default to [ISO 273 medium]({SOURCE}). No clearance entry is required."
        )
    if r.interface_id:
        try:
            clearances = resolve_clearances(a, r)
            st.caption(clearance_summary(clearances))
            if any(c.basis.startswith("Assumed") for c in clearances):
                st.caption(
                    "Unspecified screw sizes are assumed from the measured openings. Threads are not identified; size and fit can be overridden in Advanced."
                )
        except ValueError as error:
            st.warning(str(error))
    passage_controls(p)
    manufacturing_controls(p)
    if r.manufacturing_features and r.fabrication in ("3D printing", "Machined stock"):
        st.caption(
            "Printing chamfers exposed base corners; machining rounds corners and adds "
            "cutter relief to rectangular openings. These dimensions are editable concept assumptions."
        )
    hardware_controls(p)
    base_controls(p)
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
    requirement_controls(p)
