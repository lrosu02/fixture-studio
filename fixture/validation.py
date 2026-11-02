"""Checks state precisely which geometry or approximation was evaluated."""

import math
import numpy as np
import usd_brep as sm
from .contracts import Check, MM_TOL
from .intake import local_points, selected_interface
from .clearance import placed_regions, fixture_regions
from .base_mounting import expected_count


def validate(a, r, plan, bodies, cuts):
    checks = []

    def add(
        name, method, value, result="passed", units="mm", correction="", features=()
    ):
        checks.append(
            Check(
                name=name,
                method=method,
                measured=value,
                result=result,
                units=units,
                correction=correction,
                features=features,
            )
        )

    i = selected_interface(a, r)
    add(
        "Source interpretation",
        "STEP unit declaration + OCCT normalization; explicit body and stationary-interface confirmation",
        str(a.original_units) + "; bodies " + str(a.selected_bodies),
        "passed" if a.original_units and r.mounting_confirmed else "inconclusive",
    )
    expected = {(n, h) for n in range(len(plan.placements)) for h in i.hole_ids}
    actual = {(c["instance"], c["feature"]) for c in cuts}
    if plan.version >= 3:
        from .fasteners import resolve_clearances

        required = resolve_clearances(a, r)
        sizes = {c.feature_id: c.diameter for c in required}
        matched = plan.clearances == required and all(
            abs(c["diameter"] - sizes.get(c["feature"], -1)) < 1e-9 for c in cuts
        )
        base_ops = [
            op
            for op in plan.operations
            if op.purpose == "Surrounding attachment bolt clearance"
        ]
        matched = matched and all(
            abs(op.size[0] - sizes.get("base", -1)) < 1e-9 for op in base_ops
        )
        add(
            "Clearance selection",
            "Pinned ISO 273 lookup or explicit override, resolved per selected hole",
            len(required),
            "passed" if matched else "failed",
            units="choices",
        )
    add(
        "Mounting count",
        "All selected measured holes copied for every source instance",
        len(cuts),
        "passed" if actual == expected and len(cuts) == len(expected) else "failed",
        units="holes",
    )
    max_error = 0.0
    max_void_error = 0.0
    contact_error = 0.0
    for c in cuts:
        body = bodies[c["body"]]
        h = i.hole_ids.index(c["feature"])
        center = np.array(i.centers[h]) + plan.placements[c["instance"]]
        radius = c["diameter"] / 2
        max_error = max(
            max_error, float(np.linalg.norm(center - np.array(c["center"])))
        )
        stem_low, stem_high = -r.thickness, 0.0
        if plan.version >= 9:
            from .hardware import stem_range

            stem_low, stem_high = stem_range(
                r.part_hardware,
                next(v for v in required if v.feature_id == c["feature"]),
                stem_low,
                stem_high,
                "low",
            )
        for z in (stem_low + (stem_high - stem_low) * f for f in (0.1, 0.5, 0.9)):
            # Three circular sections verify native bore wall locations/axis,
            # independent of the recorded cut arguments.
            for theta in np.linspace(0, 2 * math.pi, 12, endpoint=False):
                point = (
                    float(center[0] + radius * math.cos(theta)),
                    float(center[1] + radius * math.sin(theta)),
                    z,
                )
                _, distance = sm.get_closest_point(body, point)
                max_error = max(max_error, distance)
            _, distance = sm.get_closest_point(
                body, (float(center[0]), float(center[1]), z)
            )
            max_void_error = max(max_void_error, abs(distance - radius))
        # Retained material in contact annulus, separate from alignment.
        for theta in np.linspace(0, 2 * math.pi, 32, endpoint=False):
            rad = i.contact_radii[h]
            point = (
                float(center[0] + rad * math.cos(theta)),
                float(center[1] + rad * math.sin(theta)),
                0.0,
            )
            _, distance = sm.get_closest_point(body, point)
            contact_error = max(contact_error, distance)
    add(
        "Interface alignment",
        "SMLib closest-point samples at 3 bore depths and 12 angles; measured source-to-instance transform",
        max_error,
        ("passed" if max_error < MM_TOL else "failed")
        if i.hole_ids
        else "not_evaluated",
        features=i.hole_ids,
    )
    add(
        "Bore clearance",
        "SMLib distance from axis to nearest native surface at three depths",
        max_void_error,
        ("passed" if max_void_error < MM_TOL else "failed")
        if i.hole_ids
        else "not_evaluated",
    )
    add(
        "Contact footprint",
        "Source trimmed-face annulus samples and SMLib support ring samples (not full containment proof)",
        contact_error,
        ("passed" if i.contact_ok and contact_error < MM_TOL else "failed")
        if i.hole_ids
        else "not_evaluated",
    )
    for name, b in bodies.items():
        add(
            "Kernel validity: " + name,
            "SMLib manifold + material census + positive volume",
            b.volume(),
            "passed"
            if b.is_manifold_solid()
            and b.material_census()["solid_count"] == 1
            and b.volume() > 0
            else "failed",
            units="mm³",
        )
    add(
        "Dimensional constraints",
        "Compiled stock extent, explicit thickness, gap and maximum width",
        float(plan.parameters["width_mm"]),
        "passed"
        if r.max_width is None or plan.parameters["width_mm"] <= r.max_width + MM_TOL
        else "failed",
    )
    # Explicit edge distances are measured on pre-cut stock, independent of threads.
    min_edge = float("inf")
    stocks = {op.body: op for op in plan.operations if op.kind == "stock"}
    for c in cuts:
        op = stocks.get(c["body"])
        if op:
            for axis in (0, 1):
                min_edge = min(
                    min_edge,
                    c["center"][axis] - op.origin[axis] - c["diameter"] / 2,
                    op.origin[axis]
                    + op.size[axis]
                    - c["center"][axis]
                    - c["diameter"] / 2,
                )
    add(
        "Hole edge distance",
        "Distance from bore wall to rectangular stock sides before access cuts",
        min_edge if cuts else "No part screw holes",
        ("passed" if min_edge >= 2 - MM_TOL else "failed") if cuts else "not_evaluated",
        correction="Increase stock margin or support width." if min_edge < 2 else "",
    )
    pts = local_points(a.mesh.vertices, i)
    lo = pts.min(axis=0)
    hi = pts.max(axis=0)
    overlaps = 0
    for n, p in enumerate(plan.placements):
        for q in plan.placements[n + 1 :]:
            overlap = np.minimum(hi + p, hi + q) - np.maximum(lo + p, lo + q)
            overlaps += bool(np.all(overlap > MM_TOL))
    add(
        "Repeated source envelopes",
        "Non-overlap of conservative local source bounding boxes",
        overlaps,
        "passed" if not overlaps else "inconclusive",
        units="overlaps",
    )
    for env in r.envelopes:
        overlap_volume = 0.0
        failed = False
        for p in plan.placements:
            elo = np.array(env.minimum) + p
            ehi = np.array(env.maximum) + p
            tool = sm.primitives.create_box(tuple(elo), *tuple(ehi - elo))
            for b in bodies.values():
                blo, bhi = np.array(b.bounding_box())
                if np.any(np.minimum(ehi, bhi) - np.maximum(elo, blo) <= MM_TOL):
                    continue
                try:
                    overlap_volume += abs(
                        sm.booleans.boolean_intersection(b.copy(), tool.copy()).volume()
                    )
                except RuntimeError:
                    failed = True
        add(
            "Fixture access: " + env.id,
            "SMLib fixture intersection with user-defined finite box, repeated in each instance frame; source obstruction not evaluated",
            overlap_volume,
            "inconclusive"
            if failed
            else ("passed" if overlap_volume < 0.01 else "failed"),
            units="mm³",
            correction="Move or enlarge the real opening, or correct the specified envelope."
            if failed or overlap_volume >= 0.01
            else "",
        )
    if not r.envelopes:
        add(
            "Finite access clearance",
            "No finite user-defined access volume supplied",
            "Access text only",
            "not_evaluated",
        )
    if plan.version >= 5 or plan.composition in ("l_bracket", "bridge"):
        # Verify actual native voids in the perpendicular/base bores. Merely
        # recording relief operations does not establish that the holes exist.
        base_cuts = [
            op
            for op in plan.operations
            if op.purpose == "Surrounding attachment bolt clearance"
        ]
        expected_base_count = expected_count(r, plan)
        add(
            "Base fastener count",
            "Actual base cut count compared with the requested total (separate from part holes)",
            len(base_cuts),
            "passed" if len(base_cuts) == expected_base_count else "failed",
            units="holes",
            correction=f"Generate {expected_base_count} base holes; do not substitute the part mounting-hole count.",
        )
        error, edge = 0.0, float("inf")
        feet = {
            op.body: op
            for op in plan.operations
            if (op.kind == "support" and op.id.startswith("base-foot"))
            or op.kind == "stock"
        }
        for op in base_cuts:
            axis = "xyz".index(op.axis)
            radial_axes = [k for k in range(3) if k != axis]
            foot = feet[op.id.rsplit("-bench-", 1)[0]]
            for k in radial_axes:
                edge = min(
                    edge,
                    op.origin[k] - foot.origin[k] - op.size[0] / 2,
                    foot.origin[k] + foot.size[k] - op.origin[k] - op.size[0] / 2,
                )
            stem_low, stem_high = foot.origin[axis], foot.origin[axis] + foot.size[axis]
            if plan.version >= 9:
                from .hardware import stem_range

                stem_low, stem_high = stem_range(
                    r.base_hardware,
                    next(v for v in required if v.feature_id == "base"),
                    stem_low,
                    stem_high,
                    "low" if r.base_hardware.style == "nut_pocket" else "high",
                )
            for fraction in (0.15, 0.5, 0.85):
                center = np.array(op.origin)
                center[axis] = stem_low + (stem_high - stem_low) * fraction
                _, distance = sm.get_closest_point(bodies[op.target], tuple(center))
                error = max(error, abs(distance - op.size[0] / 2))
                for theta in np.linspace(0, 2 * math.pi, 12, endpoint=False):
                    point = center.copy()
                    point[radial_axes[0]] += op.size[0] / 2 * math.cos(theta)
                    point[radial_axes[1]] += op.size[0] / 2 * math.sin(theta)
                    _, distance = sm.get_closest_point(bodies[op.target], tuple(point))
                    error = max(error, distance)
        add(
            "Base fastener geometry",
            "Native bore wall/axis samples at three base depths; all base attachments present",
            error,
            "passed"
            if len(base_cuts) == expected_base_count and error < MM_TOL
            else "failed",
        )
        if base_cuts:
            add(
                "Base fastener edge distance",
                "Bore wall to pre-cut foot boundaries in its own plane",
                edge,
                "passed" if edge >= 2 - MM_TOL else "failed",
            )
        if (
            plan.version >= 6
            and r.base_mount is None
            and plan.composition == "l_bracket"
            and expected_base_count % 2
        ):
            foot = feet["base-foot"]
            center = np.array(
                (foot.origin[0] + foot.size[0] / 2, (foot.origin[2] - r.thickness) / 2)
            )
            points = np.array([(op.origin[0], op.origin[2]) for op in base_cuts])
            symmetry_error = float("inf")
            if len(points):
                symmetry_error = float(np.linalg.norm(points - center, axis=1).min())
                for k in (0, 1):
                    for point in points:
                        reflected = point.copy()
                        reflected[k] = 2 * center[k] - reflected[k]
                        symmetry_error = max(
                            symmetry_error,
                            float(np.linalg.norm(points - reflected, axis=1).min()),
                        )
            add(
                "Base pattern symmetry",
                "Odd L-bracket pattern has a center bore and mirrored outer pairs in the usable foot",
                symmetry_error if len(points) else "missing base holes",
                "passed" if symmetry_error < MM_TOL else "failed",
                correction="Keep the outer holes symmetric and place the odd hole at the usable foot center.",
            )
    if plan.composition in ("l_bracket", "bridge") or (
        plan.version >= 7 and plan.composition == "plate"
    ):
        rear_ops = [op for op in plan.operations if op.id.startswith("rear-relief-")]
        if plan.version >= 2:
            required = (
                fixture_regions(a, i, r, plan.placements, plan.operations)
                if plan.version >= 4
                else placed_regions(a, i, r.rear_clearance, plan.placements)
            )

            def geometry_key(op):
                return (op.id, op.shape, op.axis, op.origin, op.size, op.profile)

            covered = {geometry_key(op) for op in rear_ops} == {
                geometry_key(op) for op in required
            }
            add(
                "Rear clearance coverage",
                "All measured clipped mesh components have their enclosing profile in every source placement",
                len(rear_ops),
                "passed" if covered else "failed",
                units="regions",
            )
            # Check the entire requested passage independently of the emitted cut
            # records. A shallow/missing cut must fail even when its pocket is empty.
            for passage in required:
                if (
                    passage.purpose
                    != "Through passage from selected measured rear profile"
                ):
                    continue
                from .executor import primitive

                try:
                    overlap = sum(
                        abs(
                            sm.booleans.boolean_intersection(
                                b.copy(), primitive(passage)
                            ).volume()
                        )
                        for b in bodies.values()
                    )
                    result = "passed" if overlap < 0.01 else "failed"
                except RuntimeError:
                    overlap, result = "unknown", "failed"
                add(
                    "Through passage: " + passage.id,
                    "Native intersection with the selected profile swept beyond all fixture stock/support extents",
                    overlap,
                    result,
                    units="mm³",
                    correction="Extend the selected passage through the fixture; a blind pocket does not provide exit access."
                    if result != "passed"
                    else "",
                )
        for op in rear_ops:
            if op.id.startswith("rear-relief-"):
                from .executor import primitive

                try:
                    overlap = sum(
                        abs(
                            sm.booleans.boolean_intersection(
                                b.copy(), primitive(op)
                            ).volume()
                        )
                        for b in bodies.values()
                    )
                    add(
                        "Rear protrusion clearance: " + op.id,
                        "Native fixture intersection with measured rear envelope; mesh approximation, not exact source BRep collision",
                        overlap,
                        "passed" if overlap < MM_TOL else "failed",
                        units="mm³",
                    )
                except RuntimeError:
                    add(
                        "Rear protrusion clearance: " + op.id,
                        "Native rear-envelope intersection failed",
                        "unknown",
                        "inconclusive",
                    )
    if r.part_attachment in ("cradle", "strap"):
        from .retention import validate_tray

        validate_tray(a, r, plan, bodies, add)
    add(
        "Surrounding attachment",
        "No external attachment requested; operating stability not evaluated"
        if r.surroundings == "none"
        else "Measured base holes aligned; exact base/fixture collision not evaluated"
        if r.base_mount
        else "Clamp lands or drilled bench holes generated; surrounding equipment not imported",
        r.surroundings,
        "inconclusive",
        units="relationship",
    )
    add(
        "Exact source collision",
        "OCCT source and SMLib fixture remain separate BRep domains",
        "Only interfaces and analytic envelopes evaluated",
        "not_evaluated",
    )
    add(
        "Operating performance",
        "No structural, thermal, fatigue, vibration or speed solver",
        r.motion_loads or "unknown",
        "not_evaluated",
        units="engineering",
    )
    add(
        "Export integrity",
        "Reopened SMLib USD BReps: manifold topology, body count, bounds ±0.01 mm and volume ±0.1%",
        len(bodies),
        units="bodies",
    )
    if plan.version >= 9:
        from .access import validate_access
        from .existing_base import validate_base
        from .shaped_retention import validate_retention
        from .hardware import validate_hardware
        from .process_geometry import validate_process

        validate_access(a, r, plan, bodies, add)
        validate_base(r, plan, bodies, add)
        validate_retention(a, r, plan, bodies, add)
        validate_hardware(a, r, plan, bodies, add)
        validate_process(a, r, plan, bodies, add)
    if plan.version >= 10:
        from .fillets import validate_fillets

        validate_fillets(r, plan, bodies, add)
    if plan.version >= 12:
        from .sheet_metal import validate_sheet

        validate_sheet(a, r, plan, bodies, add)
    if plan.version >= 14:
        from .custom_openings import validate_openings

        validate_openings(r, plan, bodies, add)
    if (
        r.through_access_required
        and r.defer_passages
        and not (
            r.fixture_openings
            or r.rear_passages
            or any(s.intent == "through" for s in r.access_selections)
        )
    ):
        add(
            "Deferred cable opening",
            "User may place an opening on the generated fixture in a later revision",
            "Opening has not been added",
            "not_evaluated",
            units="design intent",
        )
    return tuple(checks)
