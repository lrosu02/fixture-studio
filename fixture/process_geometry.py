"""Small, explicit process-dependent geometry rules; no material or slicer profile."""

from .contracts import Operation, Plan
from .existing_base import base_footprints


def policy(r):
    method = (r.fabrication or "").lower()
    kind = (
        "printing"
        if "print" in method
        else "machining"
        if "machin" in method
        else "unconfigured"
    )
    return {
        "enabled": r.manufacturing_features and kind != "unconfigured",
        "method": kind,
        "corner_mm": r.process_radius or min(2.0, r.thickness / 3),
        "basis": "Explicit corner size"
        if r.process_radius
        else "Concept default: min(2 mm, stock thickness / 3)",
        "rules": "45 degree external base-footprint corner chamfers"
        if kind == "printing"
        else "Rounded external base corners; circular corner relief on rectangular Z-axis access cuts"
        if kind == "machining"
        else "No automatic geometry rule for this method",
    }


def finished_feet(r, plan):
    p = policy(r)
    if not p["enabled"]:
        return []
    axis = "y" if plan.composition == "l_bracket" else "z"
    # Keep origins, extents, IDs and measured mounting centers unchanged.
    return [
        o.model_copy(
            update={
                "shape": "chamfer_box" if p["method"] == "printing" else "rounded_box",
                "corner_radius": p["corner_mm"],
                "axis": axis,
                "provenance": {
                    **o.provenance,
                    "corner": "user" if r.process_radius else "assumed",
                },
            }
        )
        for o in base_footprints(plan)
    ]


def corner_reliefs(r, plan):
    p = policy(r)
    if not p["enabled"] or p["method"] != "machining":
        return []
    radius = p["corner_mm"]
    result = []
    for o in plan.operations:
        if (
            o.kind != "relief"
            or o.shape != "box"
            or o.axis != "z"
            or o.id.startswith("process-")
        ):
            continue
        # Keep the full requested rectangular opening and add cutter run-out.
        for n, (x, y) in enumerate(
            (
                (x, y)
                for x in (o.origin[0], o.origin[0] + o.size[0])
                for y in (o.origin[1], o.origin[1] + o.size[1])
            )
        ):
            result.append(
                Operation(
                    id=f"process-corner-{o.id}-{n}",
                    kind="relief",
                    target=o.target,
                    shape="cylinder",
                    origin=(x, y, o.origin[2]),
                    size=(2 * radius, 2 * radius, o.size[2]),
                    purpose="Machining corner relief",
                    provenance={
                        "position": "derived",
                        "radius": "user" if r.process_radius else "assumed",
                    },
                )
            )
    return result


def add_process(a, r, plan):
    p = policy(r)
    if not p["enabled"]:
        return plan
    replacements = {o.id: o for o in finished_feet(r, plan)}
    ops = [replacements.get(o.id, o) for o in plan.operations]
    for o in corner_reliefs(r, plan):
        ops.append(o.model_copy(update={"depends_on": (ops[-1].id,)}))
    if finish := joined_corner_finish(r, plan):
        ops.append(finish.model_copy(update={"depends_on": (ops[-1].id,)}))
    return Plan.model_validate(
        {
            **plan.model_dump(),
            "operations": ops,
            "parameters": {
                **plan.parameters,
                "manufacturing_geometry": p["rules"],
                "process_radius_mm": p["corner_mm"],
                **(
                    {"joined_corner_finish": "Continuous base, wall and rib outline"}
                    if finish
                    else {}
                ),
            },
        }
    )


def joined_corner_finish(r, plan):
    if plan.version < 11 or plan.composition != "l_bracket" or not policy(r)["enabled"]:
        return None
    from .operation_bounds import bounds

    foot = next(o for o in finished_feet(r, plan) if o.id == "base-foot")
    stocks = [o for o in plan.operations if o.kind in ("stock", "support")]
    low = min(bounds(o)[0][1] for o in stocks) - 1
    high = max(bounds(o)[1][1] for o in stocks) + 1
    for o in stocks:
        lo, hi = bounds(o)
        if any(
            lo[k] < foot.origin[k] - 0.01
            or hi[k] > foot.origin[k] + foot.size[k] + 0.01
            for k in (0, 2)
        ):
            raise ValueError(
                "Joined corner finishing needs the full bracket inside its base footprint."
            )
    return Operation(
        id="process-joined-corners",
        kind="finish",
        target="mounting-platform",
        shape=foot.shape,
        axis="y",
        corner_radius=foot.corner_radius,
        origin=(foot.origin[0], low, foot.origin[2]),
        size=(foot.size[0], high - low, foot.size[2]),
        purpose="Continuous exterior corner finish across joined base, wall and ribs",
        provenance={
            "outline": "derived",
            "radius": "user" if r.process_radius else "assumed",
        },
    )


def validate_process(a, r, plan, bodies, add):
    if not policy(r)["enabled"]:
        return
    import usd_brep as sm
    from .executor import primitive

    if finish := joined_corner_finish(r, plan):
        square = finish.model_copy(update={"shape": "box", "corner_radius": None})
        removed = sm.booleans.boolean_difference(primitive(square), primitive(finish))
        obstruction = abs(
            sm.booleans.boolean_intersection(
                bodies[finish.target].copy(), removed
            ).volume(relative_accuracy=1e-8)
        )
        add(
            "Joined exterior corners",
            "Native intersection with full-height corner removal; no wall/rib ledges above the base",
            obstruction,
            "passed" if obstruction < 0.01 else "failed",
            units="mm³",
            correction="Apply the same exterior corner finish to the joined bracket.",
        )

    # Independent expected corner tools: inspect the native result, not operation labels.
    for foot in finished_feet(r, plan):
        original = foot.model_copy(update={"shape": "box", "corner_radius": None})
        removed = sm.booleans.boolean_difference(primitive(original), primitive(foot))
        # A neighboring upright/rib may share this corner. Its required material
        # is not a machining defect; only exposed base corners are finished.
        for other in plan.operations:
            if other.kind in ("stock", "support") and other.id != foot.id:
                removed = sm.booleans.boolean_difference(removed, primitive(other))
        obstruction = sum(
            abs(
                sm.booleans.boolean_intersection(b.copy(), removed.copy()).volume(
                    relative_accuracy=1e-8
                )
            )
            for b in bodies.values()
        )
        add(
            "Manufacturing corners: " + foot.id,
            "Native intersection with expected removed base corners",
            obstruction,
            "passed" if obstruction < 0.01 else "failed",
            units="mm³",
            correction="Preserve manufacturing corner geometry or revise the corner size.",
        )
    for op in corner_reliefs(r, plan):
        volume = abs(
            sm.booleans.boolean_intersection(
                bodies[op.target].copy(), primitive(op)
            ).volume(relative_accuracy=1e-8)
        )
        add(
            "Cutter clearance: " + op.id,
            "Native finite cutter run-out volume",
            volume,
            "passed" if volume < 0.01 else "failed",
            units="mm³",
        )
    # Preserve a complete annulus around all screw stems after corner/access cuts.
    from .hardware import sites, stem_range, axial

    for site in sites(a, r, plan):
        lo, hi = stem_range(
            site["choice"], site["clearance"], site["low"], site["high"], site["entry"]
        )
        d = site["clearance"].diameter
        ring = sm.booleans.boolean_difference(
            primitive(axial(site, lo + 0.01, hi - 0.01, d + 2)),
            primitive(axial(site, lo + 0.01, hi - 0.01, d)),
        )
        missing = abs(
            sm.booleans.boolean_difference(ring, bodies[site["target"]].copy()).volume(
                relative_accuracy=1e-8
            )
        )
        add(
            "Manufacturing screw web: " + site["id"],
            "Full native 1 mm radial stem web after all process cuts",
            missing,
            "passed" if missing < 0.01 else "failed",
            units="mm³",
            correction="Increase corner-to-hole spacing, decrease corner size, or revise stock.",
        )
