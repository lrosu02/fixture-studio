"""Manufacturing method and proposal guidance. Legacy print profiles remain readable."""

from .planning import patch_requirements, missing_questions

FDM = "3D printing"
CUSTOM = "Other / custom"


def manufacturing_guidance(fabrication, composition):
    method = (fabrication or "").lower()
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
    return {
        "fabrication": r.fabrication,
        "design_guidance": manufacturing_guidance(r.fabrication, r.composition),
        "status": "Manufacturing method for concept design; detailed manufacturability is not evaluated.",
    }


def save_manufacturing(p, fabrication):
    old = p.requirements
    changes = {"fabrication": fabrication} if old.fabrication != fabrication else {}
    updated = patch_requirements(old, changes)
    unknowns = [k for k in updated.unknowns if k != "fabrication"]
    if fabrication is None or fabrication.strip().lower() == "unknown":
        unknowns.append("fabrication")
    p.requirements = updated.model_copy(update={"unknowns": tuple(unknowns)})
    if changes:
        p.messages.append(
            {
                "role": "user",
                "content": "Manufacturing method: "
                + (fabrication or "not specified")
                + ".",
            }
        )
    p.stage = (
        "clarifying" if missing_questions(p.analysis, p.requirements) else "proposing"
    )
    p.error = None
    p.save()
