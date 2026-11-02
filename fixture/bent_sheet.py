"""A formed 90-degree L blank plus fitted, separately welded gussets.

No unfolding, bend allowance or material/tooling selection is implied by a formed STEP.
"""

import numpy as np

from .contracts import Operation, SheetBend, SheetJoint, SheetPanel, MM_TOL
from .sheet_metal import compile_sheet, joint_tools, _resequence, _resize
from .base_mounting import two_lanes


def compile_bent(a, r, require_ready=True):
    from .clearance import fixture_regions
    from .intake import selected_interface

    if r.composition != "l_bracket":
        raise ValueError(
            "Bent sheet currently supports L-brackets. Choose an L-bracket or separate cut panels for this concept."
        )
    radius = r.sheet_bend_radius or r.thickness
    t, gap = r.thickness, r.sheet_root_gap
    if gap >= radius:
        raise ValueError("Weld root gap must be smaller than the inside bend radius.")
    flat_r = r.model_copy(update={"sheet_construction": "cut_weld"})
    plan = compile_sheet(a, flat_r, require_ready, 13)
    if r.base_depth is None and r.reinforce and r.sheet_joint_style == "tab_slot_weld":
        # Leave the original tabbed weld land below the bend tangent.
        flat_r = flat_r.model_copy(
            update={"base_depth": plan.parameters["base_depth_mm"] + radius}
        )
        plan = compile_sheet(a, flat_r, require_ready, 13)
    stocks = {
        o.body: o
        for o in plan.operations
        if o.kind == "stock" and o.body in {p.body for p in plan.sheet_panels}
    }
    foot, wall = stocks["base-foot"], stocks["mounting-platform"]
    base_y = foot.origin[1] + t
    cy, cz = base_y + radius, -t - radius
    wall_lo, wall_hi = np.array(wall.origin), np.array(wall.origin) + wall.size
    foot_lo, foot_hi = np.array(foot.origin), np.array(foot.origin) + foot.size
    wall_lo[0], wall_hi[0] = foot_lo[0], foot_hi[0]
    wall_lo[1], foot_hi[2] = cy, cz
    if wall_hi[1] - cy <= t or cz - foot_lo[2] <= t:
        raise ValueError(
            "The bend radius leaves insufficient straight flange. Increase mount height/base depth or reduce radius."
        )
    stocks[wall.body] = _resize(wall, wall_lo, wall_hi)
    stocks[foot.body] = _resize(foot, foot_lo, foot_hi)
    panels = {
        name: SheetPanel(
            body=name,
            normal_axis="z" if name == wall.body else "x",
            thickness=t,
            form="bent" if name == wall.body else "flat",
        )
        for name in stocks
        if name != foot.body
    }
    bend = Operation(
        id="wall-base-bend",
        kind="stock",
        body="wall-base-bend",
        shape="quarter_bend",
        axis="x",
        origin=(foot_lo[0], base_y - t, cz),
        size=(foot.size[0], radius + t, radius + t),
        bend_radius=radius,
        purpose="Continuous 90-degree sheet bend",
        provenance={
            "radius": "user" if r.sheet_bend_radius else "assumed",
            "thickness": "user",
            "position": "derived",
        },
    )
    operations = (
        [o for o in plan.operations if o.kind == "place"]
        + list(stocks.values())
        + [bend]
    )
    for other in (bend.body, foot.body):
        operations.append(
            Operation(
                id="form-" + other,
                kind="combine",
                target=wall.body,
                other=other,
                purpose="Continuous formed sheet",
                provenance={"join": "derived"},
            )
        )
    joints = []
    for name, rib in stocks.items():
        if not name.startswith("corner-rib-"):
            continue
        operations.append(
            Operation(
                id="bend-fit-" + name,
                kind="relief",
                target=name,
                shape="bend_relief",
                axis="x",
                origin=(rib.origin[0] - 1, base_y - 1, cz),
                size=(t + 2, radius + 1, radius + 0.01),
                bend_radius=radius - gap,
                purpose="Fit gusset around the inside bend and root gap",
                provenance={"shape": "derived", "gap": "user"},
            )
        )
        for land, axis, along, low, high in (
            (foot.body, "y", 2, rib.origin[2], cz),
            (wall.body, "z", 1, cy, rib.origin[1] + rib.size[1]),
        ):
            if high - low <= 2:
                raise ValueError(
                    "The bend leaves too little straight gusset weld land; increase the bracket or reduce radius."
                )
            point = np.array(rib.origin) + np.array(rib.size) / 2
            k = "xyz".index(axis)
            point[k] = base_y if land == foot.body else -t
            start, end = point.copy(), point.copy()
            start[along], end[along] = low, high
            jid = name + "-to-" + land
            count = (
                r.sheet_tab_count
                if land == foot.body and r.sheet_joint_style == "tab_slot_weld"
                else 0
            )
            joint = SheetJoint(
                id=jid,
                owner=name,
                receiver=wall.body,
                receiver_land=land,
                axis=axis,
                seam_start=tuple(start),
                seam_end=tuple(end),
                root_gap=gap,
                tabs=tuple(f"{jid}-tab-{n}" for n in range(count)),
                slots=tuple(f"{jid}-slot-{n}" for n in range(count)),
                slot_clearance=r.sheet_slot_clearance,
            )
            joints.append(joint)
            for tab, slot in joint_tools(joint, panels, stocks, r):
                operations.extend(
                    (
                        tab,
                        Operation(
                            id="join-" + tab.id,
                            kind="combine",
                            target=name,
                            other=tab.body,
                            purpose="Integral gusset tab",
                            provenance={"join": "derived"},
                        ),
                        slot,
                    )
                )
    old_joint_ops = {oid for j in plan.sheet_joints for oid in (*j.tabs, *j.slots)}
    base_cuts = [
        o
        for o in plan.operations
        if o.purpose == "Surrounding attachment bolt clearance"
    ]
    base_positions = None
    if base_cuts and not r.base_mount:
        d = base_cuts[0].size[0]
        inset = t + d / 2 + 2
        base_positions = two_lanes(
            wall.origin[0] + inset,
            wall.origin[0] + wall.size[0] - inset,
            foot_lo[2] + d / 2 + 2,
            cz - d / 2 - 2,
            len(base_cuts),
            d,
            center_odd=True,
        )
    nbase = 0
    for op in plan.operations:
        if op.kind not in ("mount", "relief") or op.id in old_joint_ops:
            continue
        updates = {
            "target": wall.body if op.target == foot.body else op.target,
            "targets": tuple(
                dict.fromkeys(wall.body if b == foot.body else b for b in op.targets)
            ),
        }
        if (
            op.purpose == "Surrounding attachment bolt clearance"
            and base_positions is not None
        ):
            x, z = base_positions[nbase]
            updates["origin"] = (x, op.origin[1], z)
            nbase += 1
        operations.append(op.model_copy(update=updates))
    regions = {
        o.id: o
        for o in fixture_regions(
            a, selected_interface(a, r), r, plan.placements, operations
        )
    }
    operations = [
        regions[o.id].model_copy(update={"target": o.target, "targets": o.targets})
        if o.id in regions
        else o
        for o in operations
    ]
    return _resequence(
        plan,
        operations,
        sheet_panels=tuple(panels.values()),
        sheet_joints=tuple(joints),
        sheet_bends=(
            SheetBend(
                id=bend.id,
                body=wall.body,
                inner_radius=radius,
                thickness=t,
                flat_lands=(wall.body, foot.body),
            ),
        ),
        parameters={
            **plan.parameters,
            "manufacturing": "bent sheet with welded ribs",
            "sheet_construction": "bent_weld",
            "inside_bend_radius_mm": radius,
            "outside_bend_radius_mm": radius + t,
            "bend_angle_degrees": 90,
        },
    )


def validate_bends(r, plan, bodies, add):
    import usd_brep as sm
    from .executor import primitive

    for bend in plan.sheet_bends:
        op = next(o for o in plan.operations if o.id == bend.id)
        expected = primitive(op)
        actual = sm.booleans.boolean_intersection(
            bodies[bend.body].copy(), sm.primitives.create_box(op.origin, *op.size)
        )
        error = abs(
            sm.booleans.boolean_difference(expected.copy(), actual.copy()).volume(
                relative_accuracy=1e-8
            )
        )
        error += abs(
            sm.booleans.boolean_difference(actual, expected).volume(
                relative_accuracy=1e-8
            )
        )
        add(
            "Continuous sheet bend: " + bend.id,
            "Native symmetric difference against a 90-degree annular section; outside radius = inside radius + sheet thickness",
            error,
            "passed" if error < MM_TOL else "failed",
            units="mm³",
            correction="Move holes/clearances off the bend zone or revise the bend radius/flange dimensions.",
        )
    add(
        "Bending process",
        "Formed geometry only; radius must match material and tooling; no unfolding or press-brake simulation",
        "Not validated",
        "not_evaluated",
        units="manufacturing",
    )
