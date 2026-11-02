"""Bounded flat-panel assemblies. SMLib builds every tab, slot and panel.

The joint schedule describes weld intent, not weld sizing or a structural result.
There is no bend allowance, unfolding, kerf offset or weld-bead geometry.
"""

from itertools import combinations
import numpy as np

from .contracts import Operation, Plan, SheetPanel, SheetJoint, MM_TOL
from .manufacturing import is_sheet_metal


def _resequence(plan, operations, **updates):
    previous = None
    result = []
    for op in operations:
        op = op.model_copy(update={"depends_on": (previous,) if previous else ()})
        result.append(op)
        previous = op.id
    return Plan.model_validate({**plan.model_dump(), "operations": result, **updates})


def _resize(op, lo, hi):
    return op.model_copy(
        update={
            "kind": "stock",
            "target": None,
            "origin": tuple(lo),
            "size": tuple(np.array(hi) - lo),
        }
    )


def joint_tools(joint, panels, stocks, r):
    """Derive mating solids from panel lands and seam, independent of cut records."""
    if not joint.tabs:
        return []
    normal = "xyz".index(panels[joint.owner].normal_axis)
    axis = "xyz".index(joint.axis)
    along = next(k for k in range(3) if k not in (normal, axis))
    start, end = np.array(joint.seam_start), np.array(joint.seam_end)
    lo, hi = sorted((start[along], end[along]))
    margin = max(1.0, r.thickness / 2) + 2 * r.sheet_slot_clearance
    n = r.sheet_tab_count
    available = hi - lo - 2 * margin
    limit = (available - (n - 1) * margin) / n
    width = r.sheet_tab_width or min(max(6.0, 2 * r.thickness), limit)
    if width < max(2.0, r.thickness) or width > limit + 1e-9:
        raise ValueError(
            f"Joint {joint.id}: tab width/count do not fit. Increase panel dimensions or reduce tab count/width."
        )
    centers = (
        [(lo + hi) / 2]
        if n == 1
        else np.linspace(lo + margin + width / 2, hi - margin - width / 2, n)
    )
    receiver = stocks[joint.receiver]
    owner = stocks[joint.owner]
    receiver_lo = receiver.origin[axis]
    receiver_hi = receiver_lo + receiver.size[axis]
    owner_center = owner.origin[axis] + owner.size[axis] / 2
    lower = owner_center > (receiver_lo + receiver_hi) / 2
    result = []
    for index, center in enumerate(centers):
        tab_lo = np.array(owner.origin)
        tab_size = np.array(owner.size)
        tab_lo[normal], tab_size[normal] = owner.origin[normal], r.thickness
        tab_lo[along], tab_size[along] = center - width / 2, width
        tab_lo[axis] = (
            receiver_lo if lower else owner.origin[axis] + owner.size[axis] - 0.01
        )
        tab_size[axis] = receiver.size[axis] + joint.root_gap + 0.01
        slot_lo, slot_size = tab_lo.copy(), tab_size.copy()
        for k in (normal, along):
            slot_lo[k] -= r.sheet_slot_clearance
            slot_size[k] += 2 * r.sheet_slot_clearance
        slot_lo[axis], slot_size[axis] = receiver_lo - 1, receiver_hi - receiver_lo + 2
        tab = Operation(
            id=joint.tabs[index],
            kind="stock",
            body=joint.tabs[index],
            origin=tuple(tab_lo),
            size=tuple(tab_size),
            purpose="Sheet locating tab",
            provenance={
                "position": "derived",
                "width": "user" if r.sheet_tab_width else "assumed",
            },
        )
        slot = Operation(
            id=joint.slots[index],
            kind="relief",
            target=joint.receiver,
            origin=tuple(slot_lo),
            size=tuple(slot_size),
            purpose="Sheet mating through slot",
            provenance={
                "position": "derived",
                "clearance": "assumed"
                if "sheet_slot_clearance" not in r.provenance
                else r.provenance["sheet_slot_clearance"],
            },
        )
        result.append((tab, slot))
    return result


def compile_sheet(a, r, require_ready=True):
    from .planning import _compile_plan
    from .existing_base import add_base
    from .access import add_access
    from .clearance import fixture_regions
    from .intake import selected_interface

    if r.part_attachment != "screws" or r.composition not in (
        "plate",
        "rails",
        "l_bracket",
        "bridge",
    ):
        raise ValueError(
            "Sheet metal currently supports screw-mounted plates, rails, L-brackets and bridges. Hole-free sheet retention needs another construction rule."
        )
    if not 0.5 <= r.thickness <= 12:
        raise ValueError(
            "This sheet-metal route supports sheet thicknesses from 0.5 to 12 mm."
        )
    if any(
        h.style != "none" or h.driver_diameter
        for h in (r.part_hardware, r.base_hardware)
    ):
        raise ValueError(
            "Flat sheet cutting supports plain through holes. Remove recessed fastener seats/driver pockets or select a machining route."
        )
    adjusted = r
    if (
        r.composition == "l_bracket"
        and r.reinforce
        and r.sheet_joint_style == "tab_slot_weld"
        and r.base_depth is None
    ):
        margin = max(1.0, r.thickness / 2) + 2 * r.sheet_slot_clearance
        min_depth = (
            r.thickness
            + r.sheet_root_gap
            + (r.sheet_tab_count + 1) * margin
            + r.sheet_tab_count * (r.sheet_tab_width or max(6.0, 2 * r.thickness))
        )
        initial = _compile_plan(a, r, require_ready, 8, allow_sheet=True)
        adjusted = r.model_copy(
            update={"base_depth": max(initial.parameters["base_depth_mm"], min_depth)}
        )
    plan = _compile_plan(a, adjusted, require_ready, 8, allow_sheet=True)
    plan = plan.model_copy(update={"version": 12})
    t, gap = r.thickness, r.sheet_root_gap
    lip = (
        max(1.0, t / 2) + r.sheet_slot_clearance
        if r.sheet_joint_style == "tab_slot_weld"
        else 0
    )
    stocks = {o.body: o for o in plan.operations if o.kind in ("stock", "support")}
    axes = {name: "z" for name in stocks}
    if r.composition == "l_bracket":
        foot = stocks["base-foot"]
        base_y = foot.origin[1] + t
        for name, op in list(stocks.items()):
            lo, hi = np.array(op.origin), np.array(op.origin) + op.size
            if name == "mounting-platform":
                lo[1] = base_y + gap
            elif name == "base-foot":
                lo[0] -= lip
                hi[0] += lip
                hi[2] += lip
                axes[name] = "y"
            elif name.startswith("corner-rib-"):
                lo[1], hi[2] = base_y + gap, -t - gap
                axes[name] = "x"
            stocks[name] = _resize(op, lo, hi)
    elif r.composition == "bridge":
        for name, op in list(stocks.items()):
            lo, hi = np.array(op.origin), np.array(op.origin) + op.size
            if name == "mounting-platform":
                lo[0] -= lip
                hi[0] += lip
            elif name.startswith("bridge-leg-"):
                foot = stocks["base-foot-" + name[-1]]
                lo[2], hi[2] = foot.origin[2] + t + gap, -t - gap
                axes[name] = "x"
            elif name.startswith("base-foot-"):
                if name.endswith("0"):
                    hi[0] += lip
                else:
                    lo[0] -= lip
            stocks[name] = _resize(op, lo, hi)
    panels = {
        name: SheetPanel(body=name, normal_axis=axes[name], thickness=t)
        for name in stocks
    }
    joints = []

    def joint(owner, receiver, axis, along, low, high, tabbed=True):
        op, rec = stocks[owner], stocks[receiver]
        point = np.array(op.origin) + np.array(op.size) / 2
        k = "xyz".index(axis)
        point[k] = rec.origin[k] + (
            rec.size[k] if point[k] > rec.origin[k] + rec.size[k] / 2 else 0
        )
        start, end = point.copy(), point.copy()
        start[along], end[along] = low, high
        jid = owner + "-to-" + receiver
        n = (
            r.sheet_tab_count
            if tabbed and r.sheet_joint_style == "tab_slot_weld"
            else 0
        )
        joints.append(
            SheetJoint(
                id=jid,
                owner=owner,
                receiver=receiver,
                axis=axis,
                seam_start=tuple(start),
                seam_end=tuple(end),
                root_gap=gap,
                tabs=tuple(f"{jid}-tab-{i}" for i in range(n)),
                slots=tuple(f"{jid}-slot-{i}" for i in range(n)),
                slot_clearance=r.sheet_slot_clearance,
            )
        )

    if r.composition == "l_bracket":
        wall = stocks["mounting-platform"]
        joint(
            wall.body,
            "base-foot",
            "y",
            0,
            wall.origin[0],
            wall.origin[0] + wall.size[0],
        )
        for name, op in stocks.items():
            if name.startswith("corner-rib-"):
                joint(
                    name, "base-foot", "y", 2, op.origin[2], op.origin[2] + op.size[2]
                )
                joint(
                    name,
                    wall.body,
                    "z",
                    1,
                    op.origin[1],
                    op.origin[1] + op.size[1],
                    False,
                )
    elif r.composition == "bridge":
        for name, op in stocks.items():
            if name.startswith("bridge-leg-"):
                for receiver in ("mounting-platform", "base-foot-" + name[-1]):
                    joint(
                        name, receiver, "z", 1, op.origin[1], op.origin[1] + op.size[1]
                    )
    # Create the complete assembly before any cuts. Old monolithic unions disappear.
    operations = [o for o in plan.operations if o.kind == "place"] + list(
        stocks.values()
    )
    for j in joints:
        for tab, slot in joint_tools(j, panels, stocks, r):
            operations.extend(
                (
                    tab,
                    Operation(
                        id="join-" + tab.id,
                        kind="combine",
                        target=j.owner,
                        other=tab.body,
                        purpose="Integral sheet tab",
                        provenance={"join": "derived"},
                    ),
                    slot,
                )
            )
    for o in plan.operations:
        if o.kind not in ("mount", "relief"):
            continue
        if o.purpose == "Surrounding attachment bolt clearance":
            o = o.model_copy(update={"target": o.id.split("-bench-")[0]})
        elif o.kind == "relief":
            o = o.model_copy(update={"targets": tuple(stocks)})
        operations.append(o)
    width = max(o.origin[0] + o.size[0] for o in stocks.values()) - min(
        o.origin[0] for o in stocks.values()
    )
    if r.max_width and width > r.max_width + MM_TOL:
        raise ValueError(
            "Sheet slot edge lands increase the assembly beyond max_width. Increase the allowed width."
        )
    plan = _resequence(
        plan,
        operations,
        sheet_panels=tuple(panels.values()),
        sheet_joints=tuple(joints),
        parameters={
            **plan.parameters,
            "width_mm": width,
            "manufacturing": "flat sheet assembly",
            "sheet_joint_style": r.sheet_joint_style,
        },
    )
    plan = add_base(a, r, plan)
    plan = add_access(a, r, plan)
    # Recompute full-depth source clearances against the final panel bounds.
    regions = {
        o.id: o
        for o in fixture_regions(
            a,
            selected_interface(a, r),
            r,
            plan.placements,
            [o for o in plan.operations if o.kind == "stock" and o.body in panels],
        )
    }
    operations = []
    for op in plan.operations:
        if op.id in regions:
            op = regions[op.id].model_copy(update={"targets": tuple(stocks)})
        operations.append(op)
    return _resequence(plan, operations)


def manufacturing_record(r, plan):
    return {
        "units": "mm",
        "method": "Separate flat panels, assembled then welded",
        "joint_style": r.sheet_joint_style,
        "slot_clearance_per_side_mm": r.sheet_slot_clearance,
        "root_gap_mm": r.sheet_root_gap,
        "panels": [p.model_dump() for p in plan.sheet_panels],
        "joints": [j.model_dump() for j in plan.sheet_joints],
        "notes": [
            "Tabs locate parts; they do not establish joint strength.",
            "Slot clearance is an editable concept allowance, not a universal standard or kerf compensation.",
            "Review actual stock thickness, cutting process, assembly sequence, weld access and distortion.",
            "Weld size, process, filler, material and strength are not specified or validated.",
            "STEP contains assembled separate panels, without weld beads or bend unfolding.",
        ],
    }


def validate_sheet(a, r, plan, bodies, add):
    if not is_sheet_metal(r.fabrication):
        return
    import usd_brep as sm
    from .executor import primitive

    expected = compile_sheet(a, r)
    panels = {p.body: p for p in expected.sheet_panels}
    stocks = {
        o.body: o for o in expected.operations if o.kind == "stock" and o.body in panels
    }
    valid = (
        set(bodies) == set(panels)
        and plan.sheet_panels == expected.sheet_panels
        and plan.sheet_joints == expected.sheet_joints
    )
    add(
        "Sheet panel schedule",
        "Regenerated panel and joint schedule against final assembly",
        len(bodies),
        "passed" if valid else "failed",
        units="panels",
    )
    max_error = 0.0
    for name, panel in panels.items():
        if name not in bodies:
            continue
        body = bodies[name]
        axis = "xyz".index(panel.normal_axis)
        for fraction in (0.371, 0.618):
            offset = [0.0, 0.0, 0.0]
            offset[axis] = fraction * r.thickness
            moved = sm.transforms.translate(body.copy(), tuple(offset))
            overlap = abs(
                sm.booleans.boolean_intersection(body.copy(), moved).volume(
                    relative_accuracy=1e-8
                )
            )
            volume = abs(body.volume(relative_accuracy=1e-8))
            expected_volume = volume * (1 - fraction)
            max_error = max(
                max_error, abs(overlap - expected_volume) / max(1.0, volume)
            )
    add(
        "Flat sheet thickness",
        "Native overlap at two normal offsets; detects blind pockets/nonprismatic material",
        max_error,
        "passed" if max_error < 1e-5 else "failed",
        units="relative volume error",
        correction="Use through cuts and constant-thickness panels; this route cannot cut blind pockets.",
    )
    overlap = max(
        (
            abs(sm.booleans.boolean_intersection(x.copy(), y.copy()).volume())
            for x, y in combinations(bodies.values(), 2)
        ),
        default=0,
    )
    add(
        "Sheet assembly interference",
        "Pairwise native panel intersections",
        overlap,
        "passed" if overlap < MM_TOL else "failed",
        units="mm³",
    )
    tab_error = slot_error = land_error = seam_error = 0.0
    for j in expected.sheet_joints:
        if j.owner not in bodies or j.receiver not in bodies:
            tab_error = slot_error = float(1e9)
            continue
        tools = joint_tools(j, panels, stocks, r)
        axis = "xyz".index(j.axis)
        owner = stocks[j.owner]
        direction = (
            1 if owner.origin[axis] + owner.size[axis] / 2 > j.seam_start[axis] else -1
        )
        for fraction in (0.05, 0.25, 0.5, 0.75, 0.95):
            point = np.array(j.seam_start) + fraction * (
                np.array(j.seam_end) - j.seam_start
            )
            if any(
                all(
                    slot.origin[k] - 0.01
                    <= point[k]
                    <= slot.origin[k] + slot.size[k] + 0.01
                    for k in range(3)
                    if k != axis
                )
                for _, slot in tools
            ):
                continue
            _, receiver_distance = sm.get_closest_point(
                bodies[j.receiver], tuple(point)
            )
            point[axis] += direction * j.root_gap
            _, owner_distance = sm.get_closest_point(bodies[j.owner], tuple(point))
            seam_error = max(seam_error, receiver_distance, owner_distance)
        for tab, slot in tools:
            tab_error = max(
                tab_error,
                abs(
                    sm.booleans.boolean_difference(
                        primitive(tab), bodies[j.owner].copy()
                    ).volume()
                ),
            )
            slot_error = max(
                slot_error,
                abs(
                    sm.booleans.boolean_intersection(
                        primitive(slot), bodies[j.receiver].copy()
                    ).volume()
                ),
            )
            # A slot must remain enclosed by at least 1 mm of sheet, including
            # after source clearances/base holes have been cut.
            axis = "xyz".index(j.axis)
            lo, size = np.array(slot.origin), np.array(slot.size)
            for k in range(3):
                if k != axis:
                    lo[k] -= 1
                    size[k] += 2
            lo[axis] = stocks[j.receiver].origin[axis]
            size[axis] = r.thickness
            outer = primitive(
                slot.model_copy(update={"origin": tuple(lo), "size": tuple(size)})
            )
            ring = sm.booleans.boolean_difference(outer, primitive(slot))
            land_error = max(
                land_error,
                abs(
                    sm.booleans.boolean_difference(
                        ring, bodies[j.receiver].copy()
                    ).volume()
                ),
            )
    add(
        "Sheet locating tabs",
        "Native retained volume of independently regenerated full tabs",
        tab_error,
        "passed" if tab_error < MM_TOL else "failed",
        units="mm³",
    )
    add(
        "Sheet mating slots",
        "Native void of independently regenerated through slots including fit allowance",
        slot_error,
        "passed" if slot_error < MM_TOL else "failed",
        units="mm³",
    )
    add(
        "Sheet slot edge lands",
        "Native retained 1 mm rectangular border around every through slot after all cuts",
        land_error,
        "passed" if land_error < MM_TOL else "failed",
        units="mm³",
        correction="Increase panel size or move the conflicting opening/base hole; slots need an intact edge land.",
    )
    add(
        "Sheet weld seam lands",
        "Native samples on both mating lands at the specified root gap, excluding locating slots",
        seam_error,
        "passed" if seam_error < MM_TOL else "failed",
        correction="A clearance cut removed a weld land; revise the joint or opening.",
    )
    add(
        "Weld performance",
        "Weld schedule only; no bead sizing, process qualification or structural solver",
        "Not calculated",
        "not_evaluated",
        units="engineering",
    )
