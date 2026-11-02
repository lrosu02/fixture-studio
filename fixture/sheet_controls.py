"""Sheet-metal assembly intent; saving these controls never builds geometry."""

from hashlib import sha256

import streamlit as st

from .contracts import MAX_DIM
from .manufacturing import is_sheet_metal
from .planning import patch_requirements
from .selection_ui import save_selection, rerun_selection


JOINT_STYLES = {
    "tab_slot_weld": "Locating tabs & slots, then weld",
    "weld_only": "Weld-only butt joints",
}
SHEET_FIELDS = (
    "sheet_joint_style",
    "sheet_slot_clearance",
    "sheet_tab_width",
    "sheet_tab_count",
    "sheet_root_gap",
)


def sheet_controls(project):
    r = project.requirements
    if not is_sheet_metal(r.fabrication):
        return
    saved = {name: getattr(r, name) for name in SHEET_FIELDS}
    saved["locks"] = tuple(name for name in SHEET_FIELDS if name in r.locks)
    digest = sha256(str(saved).encode("utf-8")).hexdigest()[:12]
    key = f"sheet-joints-{project.id}-{digest}"
    locked = set(r.locks)
    with st.expander("Tabs & welded joints", expanded=False):
        st.caption(
            f"Sheet thickness: {r.thickness:g} mm. Change Fixture thickness (mm) below the preview to adjust it."
        )
        st.caption(
            "STEP contains separate flat panels. Tabs locate the panels for welding; "
            "they do not establish joint strength."
        )
        if locked.intersection(SHEET_FIELDS):
            st.info(
                "Some assembly settings are locked. Unlock them in Advanced before changing them."
            )
        style = st.selectbox(
            "Panel joint method",
            list(JOINT_STYLES),
            index=list(JOINT_STYLES).index(r.sheet_joint_style),
            format_func=JOINT_STYLES.get,
            key=key + "-style",
            disabled="sheet_joint_style" in locked,
        )
        changes = {"sheet_joint_style": style}
        if style == "tab_slot_weld":
            st.caption(
                "Tabs and slots are used at panel-to-base joints. Other panel seams are welded butt joints."
            )
            changes["sheet_slot_clearance"] = st.number_input(
                "Slot clearance per side (mm)",
                min_value=0.05,
                max_value=1.0,
                value=float(r.sheet_slot_clearance),
                step=0.05,
                format="%.2f",
                key=key + "-clearance",
                disabled="sheet_slot_clearance" in locked,
                help="Each side of the slot gets this clearance. 0.15 mm per side adds 0.30 mm to the matching tab dimension.",
            )
            changes["sheet_tab_width"] = (
                st.number_input(
                    "Tab width (mm; 0 = automatic)",
                    min_value=0.0,
                    max_value=float(MAX_DIM),
                    value=float(r.sheet_tab_width or 0),
                    step=0.5,
                    key=key + "-width",
                    disabled="sheet_tab_width" in locked,
                    help="Automatic width is derived by the geometry builder. Feasibility is checked when you generate.",
                )
                or None
            )
            changes["sheet_tab_count"] = st.number_input(
                "Tabs per tabbed joint",
                min_value=1,
                max_value=8,
                value=int(r.sheet_tab_count),
                step=1,
                key=key + "-count",
                disabled="sheet_tab_count" in locked,
                help="Count for each tabbed joint, rather than the total number of tabs in the fixture.",
            )
        else:
            st.caption(
                "Panels meet at welded butt joints. Saved tab dimensions are retained if you switch back."
            )
        changes["sheet_root_gap"] = st.number_input(
            "Weld root gap (mm)",
            min_value=0.0,
            max_value=1.0,
            value=float(r.sheet_root_gap),
            step=0.05,
            format="%.2f",
            key=key + "-gap",
            disabled="sheet_root_gap" in locked,
            help="Assembly gap at the modeled weld seams. This does not select a weld size or welding process.",
        )
        with st.expander("Fabrication scope & welding notes", expanded=False):
            st.caption(
                "Supported concepts: flat plates/rails, separate L-bracket wall/base/ribs, "
                "and bridge platform/legs/feet. Sheet thickness must be 0.5–12 mm, with plain "
                "through holes rather than recessed fastener seats or driver pockets."
            )
            st.caption(
                "Weld size, welding process and load capacity are not automatically established. "
                "This option does not create bent-sheet unfoldings or weld-bead solids."
            )
        if st.button("Save assembly joints", key=key + "-save"):
            try:
                changes = {
                    name: value
                    for name, value in changes.items()
                    if value != getattr(r, name)
                }
                if not changes:
                    st.info("These assembly joints are already saved.")
                    return
                updated = patch_requirements(r, changes)
                save_selection(
                    project,
                    updated,
                    project.highlights,
                    "Sheet-metal joints: "
                    + JOINT_STYLES[updated.sheet_joint_style]
                    + f"; slot clearance {updated.sheet_slot_clearance:g} mm per side"
                    + f"; tab width {updated.sheet_tab_width or 'automatic'}"
                    + f"; {updated.sheet_tab_count} tabs per tabbed joint"
                    + f"; weld root gap {updated.sheet_root_gap:g} mm.",
                )
                rerun_selection()
            except (ValueError, OSError) as error:
                st.error(str(error))
        st.caption(
            "Saving updates the requirements. Generate a revision to build and check the panels and joints."
        )
