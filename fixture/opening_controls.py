"""Preview-only surface picks; only an explicit rebuild creates fixture openings."""

from hashlib import sha256
from pathlib import Path

import streamlit as st
from plotly.offline import get_plotlyjs

from .custom_openings import (
    opening_candidate,
    remove_opening,
    resize_opening,
    resolve_pick,
)
from .viewer import assembly_figure


def opening_state(project):
    key = "fixture-opening-draft-" + project.id
    context = f"{project.id}:{project.active_id}"
    state = st.session_state.get(key)
    if not state or state["context"] != context:
        state = dict(
            context=context,
            sequence=0,
            event=None,
            preview=None,
            error=None,
            diameter=state.get("diameter", 10.0) if state else 10.0,
            opening_id=None,
        )
        st.session_state[key] = state
    state.setdefault("opening_id", None)
    return state


def apply_opening_event(project, event):
    state = opening_state(project)
    if not isinstance(event, dict) or event.get("context") != state["context"]:
        return
    sequence = event.get("sequence")
    if type(sequence) is not int or not state["sequence"] < sequence <= 2**53 - 1:
        return
    state["sequence"] = sequence
    try:
        preview = resolve_pick(project.current, event)
        state.update(event=dict(event), preview=preview, error=None)
    except (ValueError, TypeError) as error:
        state.update(event=None, preview=None, error=str(error))


def clear_opening_position(project):
    state = opening_state(project)
    state.update(sequence=state["sequence"] + 1, event=None, preview=None, error=None)


def can_place_opening(project):
    return bool(
        project.current
        and project.requirements.composition == project.current.requirements.composition
        and project.requirements.interface_id
        == project.current.requirements.interface_id
    )


def begin_opening_placement(project, opening_id=None):
    """Prepare a UI draft from a callback, before rendering the diameter widget."""
    if not can_place_opening(project):
        raise ValueError("Generate the new fixture type before placing its openings.")
    if "fixture_openings" in project.requirements.locks:
        raise ValueError("Fixture openings are locked. Unlock them in Advanced first.")
    target = next(
        (
            opening
            for opening in project.requirements.fixture_openings
            if opening.id == opening_id
        ),
        None,
    )
    if opening_id is not None and target is None:
        raise ValueError("This saved opening no longer exists.")
    state = opening_state(project)
    clear_opening_position(project)
    state["opening_id"] = opening_id
    if target:
        state["diameter"] = target.diameter
    st.session_state["fixture-opening-diameter-" + project.id] = state["diameter"]


@st.cache_resource
def _registered(source):
    return st.components.v2.component(
        "fixture_opening_picker_" + sha256(source.encode()).hexdigest()[:10],
        html="<style>.opening-picker-shell:fullscreen{background:#101820;width:100vw;height:100vh}"
        ".opening-picker-shell:fullscreen .opening-picker-plot{height:calc(100vh - 38px)!important}</style>"
        '<div class="opening-picker-shell" style="position:relative">'
        '<button class="opening-picker-fullscreen" aria-label="Fullscreen fixture preview" '
        'title="Fullscreen fixture preview" style="position:absolute;left:8px;top:8px;z-index:10;'
        'border:1px solid #3b5060;border-radius:5px;color:#dce5ed;background:#17242f;cursor:pointer">⛶</button>'
        '<div class="opening-picker-plot" style="height:510px;width:100%"></div>'
        '<p class="opening-picker-status" role="status" style="font-size:12px">'
        "Loading fixture preview…</p></div>",
        js=get_plotlyjs() + "\n" + source,
        isolate_styles=False,
    )


def opening_component():
    directory = Path(__file__).parent
    helpers = (
        (directory / "face_picker.js")
        .read_text(encoding="utf-8")
        .partition("export default function")[0]
    )
    return _registered(
        helpers + (directory / "opening_picker.js").read_text(encoding="utf-8")
    )


@st.cache_data(max_entries=6, show_spinner=False)
def opening_geometry(
    geometry_key,
    _analysis,
    _revision,
    source,
    fixture,
    evidence,
    dimensions,
    envelopes,
    _previous,
    highlights,
):
    figure = assembly_figure(
        _analysis,
        revision=_revision,
        source=source,
        fixture=fixture,
        evidence=evidence,
        dimensions=dimensions,
        envelopes=envelopes,
        previous=_previous,
        highlight_ids=highlights,
    )
    for trace in figure.data:
        if trace.type != "mesh3d":
            continue
        if trace.name in _revision.meshes:
            trace.meta = dict(opening_surface=True, opening_body=trace.name)
        elif (trace.name or "").startswith("Source ") or trace.name == "Existing base":
            trace.meta = dict(opening_surface=True)
    return figure.to_json()


def _rebuild(project, build, candidate, description):
    # The build transaction owns requirements/CAD persistence and rollback.
    # Clicking, sizing and failed candidate validation never save requirements.
    build(project, candidate, description)


def render_opening_view(
    project,
    build,
    *,
    enabled,
    source,
    fixture,
    evidence,
    dimensions,
    envelopes,
    previous,
    on_done=None,
    on_place=None,
):
    revision = project.current
    state = opening_state(project)
    locked = "fixture_openings" in project.requirements.locks
    diameter_key = "fixture-opening-diameter-" + project.id
    target = next(
        (
            opening
            for opening in project.requirements.fixture_openings
            if opening.id == state["opening_id"]
        ),
        None,
    )
    # Keep the component's sibling position stable when the toolbar is hidden.
    # Otherwise Streamlit remounts its DOM element and drops the live camera.
    with st.container(key="fixture-opening-header-" + project.id):
        diameter = state["diameter"]
        if enabled:
            st.markdown(
                "**Place a saved opening on this fixture**"
                if target
                else "**Add an opening to this fixture**"
            )
            if target:
                st.caption(
                    f"Saved opening {target.id[:6]} · Ø {target.diameter:g} mm. "
                    "Click its new position; the previous location is a reference only."
                )
            st.caption(
                "Click a flat fixture wall, base or rib side, then choose the hole diameter. "
                "Curved and sloped surfaces are unsupported. The preview does not change CAD."
            )
            diameter = st.number_input(
                "Opening diameter (mm)",
                min_value=0.5,
                max_value=500.0,
                value=float(diameter),
                step=0.5,
                key=diameter_key,
                disabled=locked,
            )
            state["diameter"] = diameter
    highlights = project.highlights or revision.requirements.mounting_hole_ids
    geometry_key = sha256(
        str(
            (
                project.id,
                revision.id,
                source,
                fixture,
                evidence,
                dimensions,
                envelopes,
                previous.id if previous else None,
                highlights,
            )
        ).encode()
    ).hexdigest()
    key = "fixture-opening-view-" + project.id
    transport = st.session_state.get(key, {})
    request = transport.get("geometry_request")
    send_geometry = (
        isinstance(request, dict)
        and request.get("key") == geometry_key
        and request.get("token") != transport.get("geometry_loaded")
    )
    result = opening_component()(
        data=dict(
            source_key=project.id,
            context=state["context"],
            revision_id=revision.id,
            sequence=state["sequence"],
            preview=state["preview"],
            diameter=diameter,
            enabled=enabled and not locked and can_place_opening(project),
            geometry_key=geometry_key,
            figure=opening_geometry(
                geometry_key,
                project.analysis,
                revision,
                source,
                fixture,
                evidence,
                dimensions,
                envelopes,
                previous,
                tuple(highlights),
            )
            if send_geometry
            else None,
            geometry_token=request["token"] if send_geometry else None,
        ),
        key=key,
        on_picked_change=lambda: apply_opening_event(
            project, st.session_state.get(key, {}).get("picked")
        ),
        on_geometry_request_change=lambda: None,
        on_geometry_loaded_change=lambda: None,
        height=550,
    )
    apply_opening_event(project, getattr(result, "picked", None))
    if state["error"]:
        st.warning(state["error"])
    if enabled:
        if state["preview"]:
            pick = state["preview"]
            st.caption(
                f"Selected part: {pick['body']} · "
                + ", ".join(
                    f"{axis.upper()} {value:.2f}"
                    for axis, value in zip("xyz", pick["center"])
                )
                + f" mm · through {pick['axis'].upper()}"
            )
        if locked:
            st.info(
                "Fixture openings are locked. Unlock them in Advanced to make changes."
            )
        if not can_place_opening(project):
            st.info("Generate the new fixture type before placing its openings.")
        if project.requirements != revision.requirements:
            st.caption("Rebuilding also applies your pending design settings.")
        if st.button(
            "Place opening and rebuild" if target else "Add opening and rebuild",
            type="primary",
            key=key + "-add",
            disabled=not state["event"]
            or locked
            or not can_place_opening(project)
            or (target is None and len(project.requirements.fixture_openings) >= 32),
        ):
            try:
                candidate = opening_candidate(
                    project, state["event"], diameter, opening_id=state["opening_id"]
                )
                _rebuild(
                    project,
                    build,
                    candidate,
                    f"{'Place' if target else 'Add'} Ø {diameter:g} mm fixture opening",
                )
            except (ValueError, OSError) as error:
                st.error(str(error))
        st.button(
            "Clear opening position",
            key=key + "-clear",
            disabled=not state["event"],
            on_click=clear_opening_position,
            args=(project,),
        )
        if on_done:
            st.button("Finish placing openings", on_click=on_done, key=key + "-done")
        st.caption(
            "Rebuilding checks the through path and a 0.5 mm geometric rim. "
            "Load capacity, cable bend radius and connector fit still need review."
        )
    saved_opening_controls(
        project,
        build,
        on_place=on_place
        or (lambda opening_id: begin_opening_placement(project, opening_id)),
    )


def saved_opening_controls(project, build, on_place=None):
    openings = project.requirements.fixture_openings
    if not openings:
        return
    locked = "fixture_openings" in project.requirements.locks
    pending = sum(opening.needs_placement for opening in openings)
    label = (
        f"Fixture openings ({len(openings)}) — {pending} need placement"
        if pending
        else f"Existing fixture openings ({len(openings)})"
    )
    with st.expander(label, expanded=bool(pending)):
        st.caption(
            "Place, resize or remove openings with an explicit rebuild. "
            "Openings marked Needs placement are not cut until positioned on this fixture."
        )
        for number, opening in enumerate(openings, 1):
            key = f"opening-edit-{project.id}-{project.active_id}-{opening.id}-{opening.diameter}"
            st.markdown(f"**Opening {number} · {opening.body}**")
            if opening.needs_placement:
                st.warning(f"Needs placement · saved diameter {opening.diameter:g} mm")
                st.caption(
                    "Previous position (reference only): "
                    + ", ".join(
                        f"{axis.upper()} {value:.2f}"
                        for axis, value in zip("xyz", opening.center)
                    )
                    + f" mm · through {opening.axis.upper()}"
                )
            if on_place:
                st.button(
                    "Place on this fixture"
                    if opening.needs_placement
                    else "Reposition",
                    key=key + "-place",
                    on_click=on_place,
                    args=(opening.id,),
                    disabled=locked or not can_place_opening(project),
                )
            if opening.needs_placement:
                if not can_place_opening(project):
                    st.caption(
                        "Generate the new fixture type first, then place this opening."
                    )
                if st.button(
                    "Remove and rebuild", key=key + "-remove", disabled=locked
                ):
                    try:
                        candidate = remove_opening(project, opening.id)
                        _rebuild(
                            project,
                            build,
                            candidate,
                            f"Remove unplaced opening {number}",
                        )
                    except (ValueError, OSError) as error:
                        st.error(str(error))
                continue
            diameter = st.number_input(
                f"Diameter · Opening {number} (mm)",
                min_value=0.5,
                max_value=500.0,
                value=float(opening.diameter),
                step=0.5,
                key=key + "-diameter",
                disabled=locked,
            )
            if st.button(
                "Resize and rebuild",
                key=key + "-resize",
                disabled=locked or diameter == opening.diameter,
            ):
                try:
                    candidate = resize_opening(project, opening.id, diameter)
                    _rebuild(
                        project,
                        build,
                        candidate,
                        f"Resize fixture opening {number} to Ø {diameter:g} mm",
                    )
                except (ValueError, OSError) as error:
                    st.error(str(error))
            if st.button("Remove and rebuild", key=key + "-remove", disabled=locked):
                try:
                    candidate = remove_opening(project, opening.id)
                    _rebuild(
                        project, build, candidate, f"Remove fixture opening {number}"
                    )
                except (ValueError, OSError) as error:
                    st.error(str(error))
