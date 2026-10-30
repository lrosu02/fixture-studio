"""Named construction rules, not part templates or model-authored coordinates.

All positions use the selected measured interface frame. L-bracket bases face
+Y; bridge bases face +Z. The interface remains at Z=0 for every composition.
"""

import numpy as np
from .contracts import Operation, Plan, MM_TOL
from .clearance import placed_regions, fixture_regions, footprint_distance
from .base_mounting import distribute_count, spaced, two_lanes

STRUCTURES = {
    "plate": (
        "Common mounting plate",
        "One continuous mounting surface.",
    ),
    "rails": (
        "Open parallel supports",
        "Separate rails leave gaps for rear access.",
    ),
    "l_bracket": (
        "L-bracket",
        "Upright mounting wall with a perpendicular base foot.",
    ),
    "bridge": (
        "Bridge support",
        "Mounting platform on two legs, open underneath.",
    ),
}


def rear_relief(points, triangles):
    """Conservative box of mesh facets clipped behind the attachment plane.

    0.3 mm padding is twice the intake tessellation tolerance, not a fit or
    strength guarantee. The exact cross-kernel collision check remains absent.
    """
    if points[:, 2].min() >= -MM_TOL:
        return None
    facets = points[np.asarray(triangles)]
    facets = facets[facets[:, :, 2].min(axis=1) < -MM_TOL]
    clipped = [facets[facets[:, :, 2] < 0]]
    for n in range(3):
        u, v = facets[:, n], facets[:, (n + 1) % 3]
        crossing = (u[:, 2] < 0) != (v[:, 2] < 0)
        u, v = u[crossing], v[crossing]
        if len(u):
            clipped.append(u + (v - u) * (-u[:, 2] / (v[:, 2] - u[:, 2]))[:, None])
    clipped = np.concatenate(clipped)
    return clipped.min(axis=0) - 0.3, clipped.max(axis=0) + 0.3


def compile_structure(
    a, r, i, pts, placements, start, end, holes, diameter, version=2, clearances=()
):
    t = r.thickness
    width, depth = end - start
    relief = rear_relief(pts, a.mesh.triangles) if version == 1 else None
    enhanced = (
        placed_regions(a, i, r.rear_clearance, placements) if version >= 2 else ()
    )
    by_hole = {c.feature_id: c for c in clearances}
    ops = [
        Operation(
            id="place",
            kind="place",
            interface_id=i.id,
            instance_ids=tuple(range(len(placements))),
            purpose="Measured interface placement",
            provenance={
                "positions": "derived",
                "quantity": r.provenance.get("quantity", "user"),
            },
        )
    ]
    name = "mounting-platform"
    previous = "place"

    def emit(**kwargs):
        nonlocal previous
        op = Operation(depends_on=(previous,), **kwargs)
        ops.append(op)
        previous = op.id

    def support(label, origin, size, shape="box"):
        emit(
            id=label,
            kind="support",
            body=label,
            target=name,
            shape=shape,
            origin=tuple(origin),
            size=tuple(size),
            purpose=label,
            provenance={"position": "derived", "size": "derived"},
        )
        emit(
            id="join-" + label,
            kind="combine",
            target=name,
            other=label,
            purpose="Connected structural union",
            provenance={"relationship": "derived"},
        )

    feet = []  # Independent native bore/edge verification uses these stock records.
    if r.composition == "l_bracket":
        height = r.mount_height or float(-start[1])
        if height < -start[1] - MM_TOL:
            raise ValueError(
                "Mount height must leave the measured part and stock margin above the base."
            )
        base_y = -height
        foot_depth = r.base_depth or max(4 * t, float(depth / 2))
        if (
            r.base_depth is None
            and r.bench_hole_count is not None
            and r.surroundings == "bolt"
        ):
            rows = (r.bench_hole_count + 1) // 2
            d = r.bench_hole_diameter
            foot_depth = max(foot_depth, t + d + 4 + (rows - 1) * (d + 2))
        if foot_depth <= 2 * t:
            raise ValueError(
                "L-bracket base depth must exceed twice the stock thickness."
            )
        emit(
            id=name,
            kind="stock",
            body=name,
            origin=(start[0], base_y - t / 4, -t),
            size=(width, end[1] - base_y + t / 4, t),
            purpose="Measured mounting wall",
            provenance={
                "extent": "derived",
                "thickness": r.provenance.get("thickness", "assumed"),
            },
        )
        foot = ((start[0], base_y - t, -foot_depth), (width, t, foot_depth))
        support("base-foot", *foot)
        feet.append(("base-foot", foot, "y"))
        if r.reinforce:
            for n, x in enumerate((start[0], end[0] - t)):
                support(
                    f"corner-rib-{n}",
                    (x, base_y - t / 4, -foot_depth),
                    (t, (end[1] - base_y) * 0.7, foot_depth - t / 2),
                    "wedge",
                )
        up_axis = "Y"
        full_width = width
    else:
        rear = -float(pts[:, 2].min())
        height = r.mount_height or max(3 * t, float(depth / 2), rear + 2 * t)
        if height <= max(2 * t, rear + t):
            raise ValueError(
                "Bridge height must exceed two stock thicknesses and leave room below rear protrusions."
            )
        if r.margin < t + 0.3:
            raise ValueError(
                "Increase stock margin above thickness + 0.3 mm to keep bridge legs outside the measured part."
            )
        extension = max(r.margin, (r.bench_hole_diameter or 0) + 4)
        emit(
            id=name,
            kind="stock",
            body=name,
            origin=(start[0], start[1], -t),
            size=(width, depth, t),
            purpose="Measured mounting platform",
            provenance={
                "extent": "derived",
                "thickness": r.provenance.get("thickness", "assumed"),
            },
        )
        for n, x in enumerate((start[0], end[0] - t)):
            support(
                f"bridge-leg-{n}",
                (x, start[1], -height - t / 4),
                (t, depth, height - t / 4),
            )
            foot_x = x - extension if n == 0 else x
            foot = ((foot_x, start[1], -height - t), (extension + t, depth, t))
            support(f"base-foot-{n}", *foot)
            feet.append((f"base-foot-{n}", foot, "z"))
        foot_depth = depth
        up_axis = "Z"
        full_width = width + 2 * extension
    if r.max_width and full_width > r.max_width + MM_TOL:
        raise ValueError(
            f"Required width including base feet {full_width:.2f} mm exceeds max_width {r.max_width:.2f} mm."
        )
    if version >= 4:
        enhanced = fixture_regions(a, i, r, placements, ops)

    # Version 1 is retained only for deterministic reproduction of old exports.
    regions = []
    if relief:
        for n, p in enumerate(placements):
            regions.append(
                (
                    f"rear-relief-{n}",
                    relief[0] + p,
                    relief[1] + p,
                    "Measured rear protrusion relief (mesh box + 0.3 mm)",
                    "derived",
                )
            )
    for n, p in enumerate(placements):
        for env in r.envelopes:
            regions.append(
                (
                    f"access-{n}-{env.id}",
                    np.array(env.minimum) + p,
                    np.array(env.maximum) + p,
                    env.purpose,
                    "user",
                )
            )
    for oid, lo, hi, purpose, origin in regions:
        if lo[2] <= 0 <= hi[2]:
            for _, hid, c, radius in holes:
                if (
                    np.linalg.norm(c[:2] - np.clip(c[:2], lo[:2], hi[:2]))
                    < radius + 0.3
                ):
                    raise ValueError(
                        f"Clearance region {oid} conflicts with contact around {hid}. Choose another mounting face or revise the region."
                    )
        emit(
            id=oid,
            kind="relief",
            target=name,
            origin=tuple(lo),
            size=tuple(hi - lo),
            purpose=purpose,
            provenance={"region": origin},
        )
    for region in enhanced:
        if region.origin[2] <= 0 <= region.origin[2] + region.size[2]:
            for _, hid, center, radius in holes:
                if footprint_distance(region, center) < radius + 0.3:
                    raise ValueError(
                        f"A rear protrusion clearance still overlaps support around mounting hole {hid}. "
                        "The shaped cut cannot preserve this contact patch. A different mounting interface or a stand-off design is needed; no holes were moved."
                    )
        emit(**region.model_dump(exclude={"depends_on"}))
    for n, hid, c, rad in holes:
        emit(
            id=f"mount-{n}-{hid}",
            kind="mount",
            target=name,
            interface_id=i.id,
            instance_ids=(n,),
            hole_ids=(hid,),
            diameter=by_hole[hid].diameter if clearances else diameter,
            origin=(0, 0, -t - 1),
            size=(1, 1, t + 2),
            purpose="Measured part fastener clearance",
            provenance={
                "pattern": "measured",
                "diameter": by_hole[hid].origin
                if clearances
                else r.provenance.get("clearance_diameter", "user"),
            },
        )
    if r.surroundings == "bolt":
        d = r.bench_hole_diameter
        if not d:
            raise ValueError("Specify bench hole diameter.")
        counts = (
            distribute_count(r.bench_hole_count, len(feet))
            if r.bench_hole_count is not None
            else [2] * len(feet)
        )
        for (foot_name, (lo, size), axis), count in zip(feet, counts):
            if axis == "y":
                # Inside the rear foot, beyond the wall. Keep side ribs clear.
                inset = t + d / 2 + 2
                if width <= 2 * inset + d + 2 or foot_depth - t < d + 4:
                    raise ValueError(
                        "Increase bracket width/margin or base depth for base fasteners and side ribs."
                    )
                positions = [
                    (start[0] + inset, lo[1] - 1, -(foot_depth + t) / 2),
                    (end[0] - inset, lo[1] - 1, -(foot_depth + t) / 2),
                ]
                if r.bench_hole_count is not None:
                    positions = [
                        (x, lo[1] - 1, z)
                        for x, z in two_lanes(
                            start[0] + inset,
                            end[0] - inset,
                            -foot_depth + d / 2 + 2,
                            -t - d / 2 - 2,
                            count,
                            d,
                            center_odd=version >= 6,
                        )
                    ]
                length = size[1] + 2
            else:
                if depth < 2 * (d + 2):
                    raise ValueError("Increase bridge depth/margin for base fasteners.")
                x = (
                    lo[0] + extension / 2
                    if foot_name.endswith("0")
                    else lo[0] + t + extension / 2
                )
                positions = [
                    (x, start[1] + d / 2 + 2, lo[2] - 1),
                    (x, end[1] - d / 2 - 2, lo[2] - 1),
                ]
                if r.bench_hole_count is not None:
                    positions = [
                        (x, y, lo[2] - 1)
                        for y in spaced(
                            start[1] + d / 2 + 2, end[1] - d / 2 - 2, count, d
                        )
                    ]
                length = size[2] + 2
            for n, pos in enumerate(positions):
                emit(
                    id=f"{foot_name}-bench-{n}",
                    kind="relief",
                    target=name,
                    shape="cylinder",
                    axis=axis,
                    origin=pos,
                    size=(d, d, length),
                    purpose="Surrounding attachment bolt clearance",
                    provenance={
                        "diameter": by_hole["base"].origin if clearances else "user",
                        "position": "derived",
                    },
                )
    return Plan(
        version=version,
        clearances=clearances,
        source_hash=a.source_hash,
        interface_id=i.id,
        composition=r.composition,
        placements=tuple(tuple(p) for p in placements),
        operations=tuple(ops),
        parameters={
            "width_mm": float(full_width),
            "depth_mm": float(depth),
            "thickness_mm": t,
            "gap_mm": r.gap,
            "clearance_diameter_mm": diameter,
            "quantity": len(placements),
            **(
                {
                    "base_hole_count": sum(
                        op.purpose == "Surrounding attachment bolt clearance"
                        for op in ops
                    )
                }
                if version >= 5
                else {}
            ),
            "mount_height_mm": height,
            "base_depth_mm": foot_depth,
            "up_axis": up_axis,
            "rear_relief": ("separate measured profiles" if enhanced else "none")
            if version >= 2
            else ("mesh-derived box" if relief else "none"),
            **(
                {
                    "rear_clearance_mm": r.rear_clearance,
                    "rear_region_count": len(enhanced),
                }
                if version >= 2
                else {}
            ),
            **(
                {"rear_passage_count": len(r.rear_passages) * len(placements)}
                if version >= 4
                else {}
            ),
        },
    )
