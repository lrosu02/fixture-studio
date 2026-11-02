"""A second measured STEP interface, rigidly placed against fixture base lands."""

import numpy as np
from .contracts import Operation, Plan, MM_TOL
from .intake import get_interface, local_points


def base_footprints(plan):
    return [
        o
        for o in plan.operations
        if (o.kind in ("support", "stock") and o.id.startswith("base-foot"))
        or (
            o.kind == "stock"
            and o.id.startswith("stock-")
            and plan.composition in ("plate", "rails")
        )
    ]


def transform(r, plan):
    axis = 1 if plan.composition == "l_bracket" else 2
    feet = base_footprints(plan)
    lo = np.min([o.origin for o in feet], axis=0)
    hi = np.max([np.array(o.origin) + o.size for o in feet], axis=0)
    anchor = (lo + hi) / 2
    anchor[axis] = lo[axis]
    if "base_anchor_x" in plan.parameters:
        anchor = np.array([plan.parameters["base_anchor_" + k] for k in "xyz"])
    basis = np.array(
        [(1, 0, 0), (0, 0, 1), (0, -1, 0)]
        if axis == 1
        else [(1, 0, 0), (0, -1, 0), (0, 0, -1)],
        dtype=float,
    )
    angle = np.deg2rad(r.base_rotation)
    rot = np.array(
        [
            [np.cos(angle), np.sin(angle), 0],
            [-np.sin(angle), np.cos(angle), 0],
            [0, 0, 1],
        ]
    )
    anchor = anchor + np.array([r.base_offset_x, r.base_offset_y, 0]) @ basis
    return anchor, rot @ basis


def measured_positions(r, plan):
    m = r.base_mount
    i = get_interface(m.analysis, m.interface_id)
    if local_points(m.analysis.mesh.vertices, i)[:, 2].min() < -MM_TOL:
        raise ValueError(
            "The selected base face has protrusions above it. Select its outer contact face."
        )
    anchor, basis = transform(r, plan)
    return {
        h: np.array(i.centers[i.hole_ids.index(h)]) @ basis + anchor for h in m.hole_ids
    }


def add_base(a, r, plan):
    if r.base_mount is None:
        return plan
    if r.surroundings != "bolt":
        raise ValueError("An existing base requires bolted surrounding attachment.")
    if r.bench_hole_count is not None and r.bench_hole_count != len(
        r.base_mount.hole_ids
    ):
        raise ValueError(
            "The requested base-hole count differs from the selected measured base holes."
        )
    axis = 1 if plan.composition == "l_bracket" else 2
    radial = [k for k in range(3) if k != axis]
    anchor, _ = transform(
        r.model_copy(update={"base_offset_x": 0, "base_offset_y": 0}), plan
    )
    positions = measured_positions(r, plan)
    diameter = next(c.diameter for c in plan.clearances if c.feature_id == "base")
    edge_allowance = diameter / 2 + 2
    if r.base_hardware.style != "none":
        from .hardware import specification

        record = next(c for c in plan.clearances if c.feature_id == "base")
        edge_allowance = max(
            edge_allowance, specification(r.base_hardware, record)["radius"] + 1.02
        )
    values = list(positions.values())
    if any(
        np.linalg.norm(u - v) < diameter + 2 - MM_TOL
        for n, u in enumerate(values)
        for v in values[n + 1 :]
    ):
        raise ValueError(
            "The measured base pattern leaves less than 2 mm between bores."
        )
    feet = base_footprints(plan)
    replacements = {}
    if len(feet) == 1:
        foot = feet[0]
        low = np.array(foot.origin)
        high = low + foot.size
        for k in radial:
            needed_low = min(p[k] for p in values) - edge_allowance
            needed_high = max(p[k] for p in values) + edge_allowance
            if plan.composition == "l_bracket" and k == 2:
                if needed_high > -r.thickness - MM_TOL:
                    raise ValueError(
                        "Base holes intersect the upright wall. Move the base pattern outward using the second in-plane offset."
                    )
                if r.base_depth is not None and needed_low < low[k] - MM_TOL:
                    raise ValueError(
                        "Base pattern exceeds the explicit base depth. Increase it or adjust base placement."
                    )
            low[k] = min(low[k], needed_low)
            high[k] = max(high[k], needed_high)
        replacements[foot.id] = foot.model_copy(
            update={"origin": tuple(low), "size": tuple(high - low)}
        )
        feet = [replacements[foot.id]]
    ops = [
        replacements.get(o.id, o)
        for o in plan.operations
        if o.purpose != "Surrounding attachment bolt clearance"
    ]
    for n, (hid, p) in enumerate(positions.items()):
        foot = next(
            (
                f
                for f in feet
                if all(
                    f.origin[k] + diameter / 2 + 2 - MM_TOL
                    <= p[k]
                    <= f.origin[k] + f.size[k] - diameter / 2 - 2 + MM_TOL
                    for k in radial
                )
            ),
            None,
        )
        if foot is None:
            raise ValueError(
                "The measured base hole does not land on a fixture foot/rail. Adjust the layout or use a common plate."
            )
        # Keep holes clear of source contact zones, independently of visual overlap.
        source = get_interface(a, plan.interface_id)
        if axis == 2 and any(
            np.linalg.norm(p[:2] - (np.array(c) + placement)[:2])
            < radius + diameter / 2 + 0.3
            for placement in plan.placements
            for c, radius in zip(source.centers, source.contact_radii)
        ):
            raise ValueError(
                "The base pattern overlaps a source mounting contact. Adjust the base placement."
            )
        origin = p.copy()
        origin[axis] = foot.origin[axis] - 1
        target = foot.target if foot.kind == "support" else foot.body
        ops.append(
            Operation(
                id=f"{foot.id}-bench-{n}",
                kind="relief",
                target=target,
                shape="cylinder",
                axis="xyz"[axis],
                origin=tuple(origin),
                size=(diameter, diameter, foot.size[axis] + 2),
                purpose="Surrounding attachment bolt clearance",
                provenance={
                    "pattern": "measured",
                    "base_source": "measured",
                    "placement": "user",
                    "diameter": "derived",
                },
            )
        )
    # Rechain after replacing generated holes; all references still precede uses.
    ops = [
        o.model_copy(update={"depends_on": (ops[n - 1].id,) if n else ()})
        for n, o in enumerate(ops)
    ]
    stocks = [o for o in ops if o.kind in ("stock", "support")]
    width = max(o.origin[0] + o.size[0] for o in stocks) - min(
        o.origin[0] for o in stocks
    )
    if r.max_width and width > r.max_width + MM_TOL:
        raise ValueError(
            "The measured base requires a wider fixture than the locked/requested maximum width."
        )
    return Plan.model_validate(
        {
            **plan.model_dump(),
            "operations": ops,
            "parameters": {
                **plan.parameters,
                "width_mm": width,
                "base_hole_count": len(positions),
                "base_source_hash": r.base_mount.analysis.source_hash,
                **{"base_anchor_" + k: float(v) for k, v in zip("xyz", anchor)},
            },
        }
    )


def validate_base(r, plan, bodies, add):
    if r.base_mount is None:
        return
    import usd_brep as sm
    from .executor import primitive

    expected = measured_positions(r, plan)
    bores = [
        o
        for o in plan.operations
        if o.purpose == "Surrounding attachment bolt clearance"
    ]
    axis = 1 if plan.composition == "l_bracket" else 2
    radial = [k for k in range(3) if k != axis]
    error = max(
        (
            min(
                (
                    np.linalg.norm(np.array(o.origin)[radial] - point[radial])
                    for o in bores
                ),
                default=float("inf"),
            )
            for point in expected.values()
        ),
        default=float("inf"),
    )
    add(
        "Existing base alignment",
        "Measured second-STEP hole centers transformed into the fixture base frame",
        float(error) if np.isfinite(error) else "Missing base holes",
        "passed" if error < MM_TOL and len(bores) == len(expected) else "failed",
    )
    obstruction = sum(
        abs(
            sm.booleans.boolean_intersection(
                bodies[o.target].copy(), primitive(o)
            ).volume()
        )
        for o in bores
    )
    add(
        "Existing base passages",
        "Native obstruction through every measured base bore",
        obstruction,
        "passed" if obstruction < 0.01 else "failed",
        units="mm³",
    )
