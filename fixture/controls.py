import json
import streamlit as st
from .contracts import Envelope, HoleFastenerChoice
from .manufacturing import FDM, CUSTOM, SHEET_METAL, is_sheet_metal, save_manufacturing
from .sheet_controls import sheet_controls
from .planning import patch_requirements, missing_questions
from .structures import STRUCTURES
from .clearance import passage_options
from .fasteners import proposed_screw_sizes, fastener_size, nominal_label
from .intake import selected_interface


def retention_controls(p):
    r = p.requirements
    if not r.interface_id or not r.mounting_confirmed:
        return
    raw = next(i for i in p.analysis.interfaces if i.id == r.interface_id)
    labels = {
        "unselected": "Choose how to retain the part",
        "screws": "Screws through selected part holes",
        "cradle": "Locating tray — no hold-down",
        "strap": "Locating tray with an external strap",
        "nest": "Contoured nest — convex envelope",
        "saddle": "Cylindrical saddle — open above",
        "collar": "Closed locating collar — axial installation",
        "split_clamp": "Split clamp with removable cap",
    }
    options = (
        ["unselected", "saddle", "collar", "split_clamp"]
        if raw.support_kind == "cylinder"
        else [
            "unselected",
            *(
                ["screws"]
                if raw.hole_ids
                and (r.mounting_hole_ids or r.part_attachment == "screws")
                else []
            ),
            "cradle",
            "strap",
            "nest",
        ]
    )
    if raw.hole_ids and "screws" not in options:
        st.caption("Select mounting holes in the 3D view to use screw mounting.")
    key = p.id + str(hash(r.model_dump_json()))
    choice = st.selectbox(
        "How should the part be held?",
        options,
        index=options.index(r.part_attachment) if r.part_attachment in options else 0,
        format_func=labels.get,
        key="retention-" + key,
    )
    if choice in ("cradle", "strap", "nest", "saddle", "collar", "split_clamp"):
        st.caption(
            "Support geometry follows measured source envelopes. Open trays/saddles have no hold-down. Nests use a convex footprint; collars need axial installation. Wall/fit dimensions are concept defaults, not strength validation."
        )
        clearance = st.number_input(
            "Part-to-wall clearance (mm)",
            0.3,
            10.0,
            float(r.locating_clearance),
            key="fit-" + key,
        )
        wall = st.number_input(
            "Locating wall thickness (mm)",
            0.5,
            100.0,
            float(r.locating_wall),
            key="wall-" + key,
        )
        height = (
            st.number_input(
                "Locating wall height (mm; 0 = derive)",
                0.0,
                500.0,
                float(r.locating_height or 0),
                key="height-" + key,
            )
            or None
        )
        width, thickness = r.strap_width, r.strap_thickness
        length = r.retention_length
        fastener = r.retention_fastener
        if choice in ("saddle", "collar", "split_clamp"):
            length = (
                st.number_input(
                    "Cylindrical support length (mm; 0 = derive)",
                    0.0,
                    2000.0,
                    float(length or 0),
                )
                or None
            )
        if choice == "split_clamp":
            fastener = st.text_input("Clamp joining screw size", fastener or "") or None
        if choice == "strap":
            width = (
                st.number_input(
                    "Strap width (mm; 0 = unknown)",
                    0.0,
                    500.0,
                    float(width or 0),
                    key="strap-width-" + key,
                )
                or None
            )
            thickness = (
                st.number_input(
                    "Strap thickness (mm; 0 = unknown)",
                    0.0,
                    50.0,
                    float(thickness or 0),
                    key="strap-thickness-" + key,
                )
                or None
            )
            st.caption(
                "Two through slots route the strap across the local X direction and over the part. Slots add 1 mm to the supplied strap width and thickness; underside threading access is needed."
            )
    if choice != "unselected" and st.button("Apply part retention"):
        try:
            changes = {"part_attachment": choice}
            if choice in ("cradle", "strap", "nest", "saddle", "collar", "split_clamp"):
                changes.update(
                    composition="plate",
                    locating_clearance=clearance,
                    locating_wall=wall,
                    locating_height=height,
                    strap_width=width,
                    strap_thickness=thickness,
                    retention_length=length,
                    retention_fastener=fastener,
                )
            p.requirements = patch_requirements(r, changes)
            p.messages.append(
                dict(
                    role="user",
                    content="Part retention: "
                    + labels[choice]
                    + ". "
                    + (
                        f"Wall clearance {clearance:g} mm, thickness {wall:g} mm, height {height or 'derived'}; strap width {width}, thickness {thickness} mm."
                        if choice
                        in (
                            "cradle",
                            "strap",
                            "nest",
                            "saddle",
                            "collar",
                            "split_clamp",
                        )
                        else ""
                    ),
                )
            )
            p.save()
            st.rerun()
        except ValueError as error:
            st.error(str(error))


def screw_size_controls(p):
    r = p.requirements
    if not r.interface_id or not r.mounting_confirmed or r.part_attachment != "screws":
        return
    interface = selected_interface(p.analysis, r)
    groups = {}
    for hid, diameter in zip(interface.hole_ids, interface.diameters):
        groups.setdefault(f"{diameter:.3f}", []).append(hid)
    old = {h: choice for choice in r.hole_fasteners for h in choice.hole_ids}
    assignments = []
    st.markdown("**Proposed screw size**")
    st.caption("Suggestions use the measured opening; they do not identify threads.")
    for size, holes in groups.items():
        choices = proposed_screw_sizes(float(size))
        present = {old[h].nominal if h in old else r.nominal_fastener for h in holes}
        nominal = present.pop() if len(present) == 1 else None
        try:
            key = fastener_size(nominal)
            nominal = nominal_label(key) if key is not None else None
        except ValueError:
            pass
        options = ["", *choices, "Other"]
        default = nominal if nominal in choices else "Other" if nominal else ""
        widget_key = f"screw-{p.id}-{size}-{hash(r.model_dump_json())}"
        choice = st.selectbox(
            f"Screw size · Ø{size} mm ({len(holes)} holes)",
            options,
            index=options.index(default),
            format_func=lambda v, choices=tuple(choices): (
                v
                if v
                else "Automatic" + (f" — suggested {choices[0]}" if choices else "")
            ),
            key=widget_key,
        )
        clearance = None
        if choice == "Other":
            choice = (
                st.text_input(
                    f"Other screw size · Ø{size} mm",
                    nominal or "",
                    key=widget_key + "-other",
                )
                or None
            )
            existing = {old[h].clearance_diameter for h in holes if h in old}
            value = existing.pop() if len(existing) == 1 else None
            clearance = (
                st.number_input(
                    f"Custom clearance · Ø{size} mm (0 = automatic)",
                    0.0,
                    100.0,
                    float(value or 0),
                    key=widget_key + "-custom",
                )
                or None
            )
        assignments.append(
            HoleFastenerChoice(
                hole_ids=tuple(holes),
                nominal=choice or None,
                clearance_diameter=clearance,
            )
        )
    if r.clearance_diameter is not None:
        st.caption(
            f"Your {r.clearance_diameter:g} mm mounting clearance override remains active. Set it to 0 in Advanced to use automatic clearance."
        )
    if st.button("Apply screw sizes"):
        try:
            candidate = patch_requirements(r, {"hole_fasteners": tuple(assignments)})
            from .fasteners import resolve_clearances

            resolve_clearances(p.analysis, candidate)
            p.requirements = candidate
            p.messages.append(
                {
                    "role": "user",
                    "content": "Screw sizes for selected holes: "
                    + "; ".join(
                        f"{', '.join(c.hole_ids)}: {c.nominal or 'automatic'}"
                        for c in assignments
                    ),
                }
            )
            p.save()
            st.rerun()
        except ValueError as error:
            st.error(str(error))


def passage_controls(p):
    if p.requirements.composition not in ("plate", "l_bracket", "bridge"):
        return
    try:
        choices = passage_options(p.analysis, p.requirements)
    except ValueError as error:
        st.warning("Could not measure rear passage profiles: " + str(error))
        return
    if not choices:
        return
    labels = {
        c[
            "id"
        ]: f"Recess {n + 1} · {c['width_mm']:.1f} × {c['height_mm']:.1f} mm · X {c['center_xy'][0]:.1f}, Y {c['center_xy'][1]:.1f}"
        for n, c in enumerate(choices)
    }
    with st.expander("Wire and tool passages", expanded=False):
        st.caption(
            "Existing rear recesses may be blind pockets. Choose which should open all the way through the fixture, or request this in the conversation. Their measured outlines are preserved."
        )
        selected = st.multiselect(
            "Recesses to make through",
            list(labels),
            default=[x for x in p.requirements.rear_passages if x in labels],
            format_func=labels.get,
            key="rear-passages-" + p.id + str(hash(p.requirements.model_dump_json())),
        )
        if st.button("Apply through passages"):
            try:
                p.requirements = patch_requirements(
                    p.requirements,
                    {
                        "rear_passages": tuple(selected),
                        "through_access_required": bool(selected),
                    },
                )
                p.messages.append(
                    {
                        "role": "user",
                        "content": "Make these measured rear recesses through passages: "
                        + (
                            ", ".join(labels[x] for x in selected)
                            or "none (measured-depth relief only)"
                        ),
                    }
                )
                p.save()
                st.rerun()
            except ValueError as error:
                st.error(str(error))
        st.caption(
            "Generate a revision to apply this choice. Through access is checked against fixture material; cable bend radius and connector fit are separate requirements."
        )


def requirement_controls(p):
    r = p.requirements
    with st.expander("Advanced — requirements and assumptions", expanded=False):
        form_id = str(hash(r.model_dump_json()))
        with st.form("requirements-" + form_id):

            def txt(label, field):
                return (
                    st.text_input(label, getattr(r, field) or "", key=field + form_id)
                    or None
                )

            changes = {}
            changes["purpose"] = txt("Purpose", "purpose")
            changes["quantity"] = st.number_input("Quantity", 1, 24, r.quantity or 1)
            changes["layout"] = st.selectbox(
                "Layout", ["row", "grid"], index=["row", "grid"].index(r.layout)
            )
            changes["columns"] = st.number_input("Grid columns", 1, 24, r.columns)
            changes["composition"] = st.selectbox(
                "Structure",
                list(STRUCTURES),
                index=list(STRUCTURES).index(r.composition),
                format_func=lambda key: STRUCTURES[key][0],
            )
            for label, field in [
                ("Mount height (mm; 0 = derive from part)", "mount_height"),
                ("L-bracket base depth (mm; 0 = derive from part)", "base_depth"),
            ]:
                changes[field] = (
                    st.number_input(label, 0.0, 2000.0, float(getattr(r, field) or 0))
                    or None
                )
            changes["reinforce"] = st.checkbox(
                "Triangular side ribs for L-brackets", r.reinforce
            )
            changes["rear_clearance"] = st.number_input(
                "Rear protrusion clearance (mm)",
                0.3,
                10.0,
                float(r.rear_clearance),
                step=0.1,
            )
            st.caption(
                "Separate shaped cutouts clear geometry already in the STEP. The 0.3 mm minimum accounts for the source mesh approximation; future wire/tool space is a separate choice."
            )
            st.caption(
                "L-bracket height: mounting origin above base top. Bridge height: mounting plane above base top. Derived dimensions are concept defaults, not load sizing."
            )
            for label, field in [
                ("Part gap (mm)", "gap"),
                ("Stock thickness (mm)", "thickness"),
                ("Stock margin (mm)", "margin"),
            ]:
                changes[field] = st.number_input(
                    label,
                    min_value=0.1 if field != "gap" else 0.0,
                    max_value=500.0,
                    value=float(getattr(r, field)),
                )
            changes["max_width"] = (
                st.number_input(
                    "Maximum width (mm; 0 = unset)",
                    0.0,
                    2000.0,
                    float(r.max_width or 0),
                )
                or None
            )
            changes["clearance_diameter"] = (
                st.number_input(
                    "Custom mounting clearance (mm; 0 = automatic ISO 273)",
                    0.0,
                    100.0,
                    float(r.clearance_diameter or 0),
                    step=0.1,
                )
                or None
            )
            changes["clearance_fit"] = st.selectbox(
                "Automatic clearance fit",
                ["fine", "medium", "coarse"],
                index=["fine", "medium", "coarse"].index(r.clearance_fit),
            )
            st.caption(
                "Default: ISO 273 medium/normal. Custom diameters override the table. No printer compensation is added."
            )
            changes["mounting_confirmed"] = st.checkbox(
                "I confirm this is the stationary face and highlighted features are fastener holes",
                r.mounting_confirmed,
            )
            changes["nominal_fastener"] = txt(
                "Nominal thread / fastener (unknown accepted)", "nominal_fastener"
            )
            changes["engagement"] = txt(
                "Allowable engagement (unknown accepted)", "engagement"
            )
            changes["bench_fastener"] = txt(
                "Base fastener (blank = automatic)", "bench_fastener"
            )
            changes["surroundings"] = st.selectbox(
                "Attachment to surroundings",
                ["unknown", "clamp", "bolt", "none"],
                index=["unknown", "clamp", "bolt", "none"].index(r.surroundings),
                format_func=lambda value: (
                    "None — free floating" if value == "none" else value
                ),
            )
            changes["bench_hole_diameter"] = (
                st.number_input(
                    "Custom base clearance (mm; 0 = automatic ISO 273)",
                    0.0,
                    100.0,
                    float(r.bench_hole_diameter or 0),
                    step=0.5,
                )
                or None
            )
            changes["bench_hole_count"] = (
                st.number_input(
                    "Total base mounting holes (0 = automatic)",
                    min_value=0,
                    value=int(r.bench_hole_count or 0),
                    help="Fixture-to-base holes, separate from the selected part holes. Four makes a 2 × 2 L-bracket base pattern.",
                )
                or None
            )
            for label, field in [
                (
                    "Motion, attached loads and continuous operation (unknown accepted)",
                    "motion_loads",
                ),
                ("Access needs (unknown accepted)", "access"),
                ("Appearance", "appearance"),
            ]:
                changes[field] = txt(label, field)
            locks = st.multiselect(
                "Lock requirement values",
                [
                    "purpose",
                    "quantity",
                    "layout",
                    "columns",
                    "gap",
                    "thickness",
                    "margin",
                    "max_width",
                    "interface_id",
                    "clearance_diameter",
                    "clearance_fit",
                    "nominal_fastener",
                    "hole_fasteners",
                    "bench_fastener",
                    "bench_hole_diameter",
                    "bench_hole_count",
                    "composition",
                    "mount_height",
                    "base_depth",
                    "reinforce",
                    "rear_clearance",
                    "rear_passages",
                    "through_access_required",
                    "mounting_hole_ids",
                    "fabrication",
                    "sheet_joint_style",
                    "sheet_construction",
                    "sheet_bend_radius",
                    "sheet_slot_clearance",
                    "sheet_tab_width",
                    "sheet_tab_count",
                    "sheet_root_gap",
                    "moving_components",
                    "cable_routing",
                    "service_access",
                    "motion_loads",
                ],
                default=[k for k in r.locks if k not in ("material", "print_settings")],
            )
            locks.extend(k for k in r.locks if k in ("material", "print_settings"))
            st.caption("\n".join(r.assumptions))
            changes["assumptions_accepted"] = st.checkbox(
                "I accept the visible assumptions for a concept design",
                r.assumptions_accepted,
            )
            if st.form_submit_button("Save requirements"):
                try:
                    changed = {k: v for k, v in changes.items() if v != getattr(r, k)}
                    base = r.model_copy(
                        update={"locks": tuple(k for k in r.locks if k in locks)}
                    )
                    updated = patch_requirements(base, changed)
                    unknowns = tuple(
                        k
                        for k in (
                            "motion_loads",
                            "nominal_fastener",
                            "engagement",
                        )
                        if getattr(updated, k) is None
                        or getattr(updated, k).lower() == "unknown"
                    )
                    p.requirements = updated.model_copy(
                        update={"locks": tuple(locks), "unknowns": unknowns}
                    )
                    p.stage = (
                        "clarifying"
                        if missing_questions(p.analysis, p.requirements)
                        else "proposing"
                    )
                    p.error = None
                    p.save()
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
        with st.expander("Clearance volumes (optional)"):
            st.caption(
                "Optional space to keep clear for wires, tools or moving parts. Ask the design conversation to define it, or enter a box in the displayed mounting frame. Crossing stock creates an opening if mounting contact is preserved."
            )
            region = st.text_area(
                "Clearance boxes (advanced JSON)",
                json.dumps([e.model_dump() for e in r.envelopes], indent=2),
                height=120,
            )
            if st.button("Apply access regions"):
                try:
                    envs = tuple(Envelope.model_validate(e) for e in json.loads(region))
                    p.requirements = patch_requirements(r, {"envelopes": envs})
                    p.save()
                    st.rerun()
                except Exception as error:
                    st.error(str(error))


def manufacturing_controls(p):
    r = p.requirements
    key = f"manufacturing-{p.id}-{hash(r.model_dump_json())}"
    locked = "fabrication" in r.locks
    with st.expander("How the fixture will be made", expanded=r.fabrication is None):
        st.caption(f"Saved method: {r.fabrication or 'not specified'}")
        processes = [None, "unknown", FDM, "Machined stock", SHEET_METAL, CUSTOM]
        current = (
            FDM
            if r.fabrication == "3D printing (FDM/FFF)"
            else SHEET_METAL
            if is_sheet_metal(r.fabrication)
            else r.fabrication
        )
        process = st.selectbox(
            "Manufacturing method",
            processes,
            index=processes.index(current)
            if current in processes
            else processes.index(CUSTOM),
            format_func=lambda v: (
                "Choose a method"
                if v is None
                else "Decide later"
                if v == "unknown"
                else v
            ),
            key=key + "-process",
            disabled=locked,
        )
        if process == CUSTOM:
            process = (
                st.text_input(
                    "Custom manufacturing method",
                    current if current not in processes else "",
                    key=key + "-custom-process",
                    disabled=locked,
                ).strip()
                or None
            )
        st.caption(
            "The method guides design proposals. Detailed manufacturing validation remains outside this concept tool."
        )
        if r.manufacturing_features and r.fabrication in (
            "3D printing",
            "Machined stock",
        ):
            st.caption(
                "Printing adds chamfers to exposed base corners. Machining rounds corners "
                "and adds cutter relief. Adjust these dimensions in Advanced."
            )
        if locked:
            st.caption(
                "The manufacturing method is locked. Unlock fabrication before changing it."
            )
        if st.button("Save manufacturing", key=key + "-save", disabled=locked):
            try:
                save_manufacturing(p, process)
                from .selection_ui import rerun_selection

                rerun_selection()
            except (ValueError, OSError) as error:
                st.error(str(error))
    sheet_controls(p)


def fillet_controls(p):
    r = p.requirements
    if is_sheet_metal(r.fabrication):
        return
    with st.expander("Rib-to-base fillets", expanded=False):
        st.caption(
            "Round the inward joints on ribbed L-brackets. Applies when you generate or rebuild."
        )
        key = f"fillets-{p.id}-{r.auto_rib_fillets}-{r.rib_fillet_radius}"
        enabled = st.checkbox(
            "Automatic rib fillets", r.auto_rib_fillets, key=key + "-enabled"
        )
        radius = st.number_input(
            "Fillet radius (mm; 0 = automatic)",
            0.0,
            2.0,
            float(r.rib_fillet_radius or 0),
            step=0.1,
            key=key + "-radius",
            disabled=not enabled,
        )
        st.caption(
            "Automatic radius: up to 1.5 mm and one quarter of thickness, reduced for smaller brackets. Other edges stay unchanged."
        )
        if st.button("Save fillet settings", key=key + "-save"):
            try:
                from .selection_ui import save_selection, rerun_selection

                updated = patch_requirements(
                    r,
                    {"auto_rib_fillets": enabled, "rib_fillet_radius": radius or None},
                )
                save_selection(
                    p,
                    updated,
                    p.highlights,
                    f"Rib fillets: {'automatic' if enabled else 'off'}; radius {radius or 'derived'}.",
                )
                rerun_selection()
            except (ValueError, OSError) as error:
                st.error(str(error))
