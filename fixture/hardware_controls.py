"""Optional hardware UI; geometry and feasibility remain backend decisions."""

from hashlib import sha256

import streamlit as st

from .contracts import HardwareChoice
from .hardware import TABLES
from .planning import patch_requirements


STYLES = {
    "none": "No recess — through hole only",
    "counterbore": "Counterbore — socket head",
    "countersink": "Countersink — 90° head",
    "nut_pocket": "Hex nut pocket — anti-rotation",
}


def _choice_controls(project, field, label):
    current = getattr(project.requirements, field)
    locked = field in project.requirements.locks
    digest = sha256(current.model_dump_json().encode("utf-8")).hexdigest()[:12]
    key = f"hardware-{project.id}-{field}-{digest}"
    st.markdown(f"**{label} fasteners**")
    if locked:
        st.caption(
            "This hardware choice is locked. Unlock it in Advanced to change it."
        )
    style = st.selectbox(
        f"{label} fastener recess",
        list(STYLES),
        index=list(STYLES).index(current.style),
        format_func=STYLES.get,
        key=key + "-style",
        disabled=locked,
    )
    diameter = depth = None
    if style != "none":
        custom = st.checkbox(
            f"Custom {label.lower()} recess dimensions",
            value=current.diameter is not None or current.depth is not None,
            key=key + "-custom",
            disabled=locked,
        )
        if custom:
            dimension = (
                "nut width across flats" if style == "nut_pocket" else "head diameter"
            )
            diameter = (
                st.number_input(
                    f"{label} {dimension} (mm; 0 = profile)",
                    min_value=0.0,
                    value=float(current.diameter or 0),
                    step=0.1,
                    key=key + "-diameter-" + style,
                    disabled=locked,
                )
                or None
            )
            if style != "countersink":
                depth = (
                    st.number_input(
                        f"{label} recess depth (mm; 0 = profile)",
                        min_value=0.0,
                        value=float(current.depth or 0),
                        step=0.1,
                        key=key + "-depth",
                        disabled=locked,
                    )
                    or None
                )
        if style == "countersink":
            st.caption(
                "90° countersink depth is derived from the head diameter and each through bore."
            )
        if style == "nut_pocket":
            st.caption(
                "The hex pocket prevents rotation. A base pocket needs the mating base to cover its "
                "opening for axial capture; a part pocket needs an external cover or washer. "
                "Retention strength is not established."
            )
    driver = st.checkbox(
        f"Check {label.lower()} screwdriver access",
        value=current.driver_diameter is not None,
        key=key + "-driver",
        disabled=locked,
    )
    driver_diameter = None
    driver_reach = current.driver_reach
    if driver:
        st.caption(
            "Enter your tool's diameter. The finite approach path is checked when you generate."
        )
        driver_diameter = st.number_input(
            f"{label} screwdriver diameter (mm)",
            min_value=0.0,
            value=float(current.driver_diameter or 0),
            step=0.1,
            key=key + "-driver-diameter",
            disabled=locked,
        )
        driver_reach = st.number_input(
            f"{label} screwdriver reach (mm)",
            min_value=0.1,
            max_value=500.0,
            value=float(current.driver_reach),
            step=1.0,
            key=key + "-driver-reach",
            disabled=locked,
        )
    return (
        current
        if locked
        else dict(
            style=style,
            diameter=diameter,
            depth=depth,
            driver_diameter=driver_diameter,
            driver_reach=driver_reach,
        )
    )


def hardware_controls(project):
    with st.expander("Fastener recesses and tool access", expanded=False):
        st.caption(
            "Optional seats for screw heads or nuts. Part seats use the selected mounting holes; "
            "base seats require bolted base attachment. Saving updates requirements; generate a "
            "revision to build and check the change."
        )
        profiles = "; ".join(
            f"{name}: " + ", ".join(f"M{size:g}" for size in TABLES[style])
            for style, name in (
                ("counterbore", "ISO 4762 counterbores"),
                ("countersink", "DIN 7991 legacy countersinks"),
                ("nut_pocket", "DIN 934 legacy nuts"),
            )
        )
        st.caption(
            "Manufacturer profiles — "
            + profiles
            + ". Other sizes need custom dimensions."
        )
        st.caption(
            "Profile fit allowances: head diameter +0.5 mm, nut flats +0.3 mm, "
            "counterbore/nut depth +0.2 mm. Custom values override these concept allowances."
        )
        drafts = {"part_hardware": _choice_controls(project, "part_hardware", "Part")}
        st.divider()
        drafts["base_hardware"] = _choice_controls(project, "base_hardware", "Base")
        if st.button("Save fastener accommodations", key="save-hardware-" + project.id):
            previous = project.requirements
            try:
                for field, draft in drafts.items():
                    if isinstance(draft, dict) and draft["driver_diameter"] == 0:
                        raise ValueError(
                            f"Enter a positive {field.split('_')[0]} screwdriver diameter, "
                            "or turn off its access check."
                        )
                choices = {
                    field: HardwareChoice.model_validate(draft)
                    for field, draft in drafts.items()
                }
                changes = {
                    field: choice
                    for field, choice in choices.items()
                    if choice != getattr(previous, field)
                }
                if not changes:
                    st.info("These fastener accommodations are already saved.")
                    return
                candidate = patch_requirements(previous, changes)
                project.requirements = candidate
                try:
                    project.save()
                except (OSError, ValueError):
                    project.requirements = previous
                    raise
                st.rerun()
            except (ValueError, OSError) as error:
                st.error(str(error))
