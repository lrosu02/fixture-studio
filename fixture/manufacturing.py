"""Manufacturing method and proposal guidance. Legacy print profiles remain readable."""

FDM = "3D printing"
CUSTOM = "Other / custom"
SHEET_METAL = "Sheet metal — tabs & welding"


def is_sheet_metal(fabrication):
    return "sheet metal" in (fabrication or "").lower().replace("-", " ")


def manufacturing_guidance(fabrication, composition):
    method = (fabrication or "").lower()
    if is_sheet_metal(fabrication):
        return "Separate flat sheet panels with locating tabs/slots or butt joints for welding. Review cutting and stock tolerances, assembly order and welding distortion; weld size and strength are not calculated."
    if "print" in method:
        return (
            "Printing concept: each disconnected rail is a separate printed part and needs its own base attachment."
            if composition == "rails"
            else "Printing concept: one connected body can be a single printed part; ribs can support an L-bracket corner. Review overhangs and access when choosing the build orientation."
        ) + " Build orientation, supports and strength are not automatically verified."
    if "machin" in method:
        return (
            "Machining concept: planar stock and straight through-cuts; cutter access and workholding need review."
            if composition in ("plate", "rails")
            else "Machining concept: multiple setups may be needed for perpendicular faces, ribs and base holes. Internal corners, cutter access and workholding need review."
        )
    return ""


def manufacturing_record(r):
    from .process_geometry import policy

    return {
        "fabrication": r.fabrication,
        "design_guidance": manufacturing_guidance(r.fabrication, r.composition),
        "status": "Manufacturing method for concept design; detailed manufacturability is not evaluated.",
        "geometry_policy": policy(r),
    }


def save_manufacturing(p, fabrication):
    from .planning import patch_requirements
    from .selection_ui import save_selection

    old = p.requirements
    changes = {"fabrication": fabrication} if old.fabrication != fabrication else {}
    if not old.manufacturing_features:
        changes["manufacturing_features"] = True
    updated = patch_requirements(old, changes)
    unknowns = [k for k in updated.unknowns if k != "fabrication"]
    if fabrication is None or fabrication.strip().lower() == "unknown":
        unknowns.append("fabrication")
    return save_selection(
        p,
        updated.model_copy(update={"unknowns": tuple(unknowns)}),
        p.highlights,
        "Manufacturing method: " + (fabrication or "not specified") + ".",
    )
