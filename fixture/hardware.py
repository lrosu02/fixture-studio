"""Bounded fastener seats and finite tool envelopes; built only by SMLib."""

import math
import numpy as np
from .contracts import Operation, Plan
from .fasteners import nominal_size, resolve_clearances
from .intake import selected_interface
from .existing_base import base_footprints

# Manufacturer product dimensions, not interchangeable standards or strength data.
# Fit additions below are visible concept assumptions, not values in these tables.
SOURCES = {
    "counterbore": (
        "ISO 4762 / Bossard BN 3",
        "https://www.tme.eu/Document/03d4301a0ba62459eae87221acaaf1ae/BN3.pdf",
    ),
    "countersink": (
        "DIN 7991 / Bossard BN 616 (legacy profile)",
        "https://www.tme.eu/Document/8d07529a1413d6e53f44b64cc7bb02f5/BN616-IT.pdf",
    ),
    "nut_pocket": (
        "DIN 934 / Bossard BN 629 (legacy profile)",
        "https://media.distrelec.com/Web/Downloads/_t/ds/1241613_eng_tds.pdf",
    ),
}
TABLES = {
    "counterbore": {3: (5.5, 3), 4: (7, 4), 5: (8.5, 5), 6: (10, 6)},
    "countersink": {3: (6, 1.7), 4: (8, 2.3), 5: (10, 2.8), 6: (12, 3.3), 8: (16, 4.4)},
    "nut_pocket": {3: (5.5, 2.4), 4: (7, 3.2), 5: (8, 4), 6: (10, 5), 8: (13, 6.5)},
}


def specification(choice, clearance):
    if choice.style == "none":
        return dict(
            width=clearance.diameter,
            depth=0.0,
            radius=clearance.diameter / 2,
            basis="Through bore",
        )
    nominal = None
    try:
        nominal = nominal_size(clearance.nominal)
    except ValueError:
        pass
    standard = TABLES[choice.style].get(nominal)
    if standard is None and (
        choice.diameter is None
        or (choice.depth is None and choice.style != "countersink")
    ):
        raise ValueError(
            "This fastener seat needs an explicit head diameter/nut width and depth; its nominal size has no pinned hardware profile."
        )
    width = choice.diameter or (
        standard[0] + (0.3 if choice.style == "nut_pocket" else 0.5)
    )
    depth = (
        (width - clearance.diameter) / 2
        if choice.style == "countersink"
        else choice.depth or standard[1] + 0.2
    )
    if (
        choice.style == "countersink"
        and choice.depth is not None
        and abs(choice.depth - depth) > 0.01
    ):
        raise ValueError(
            "A 90 degree countersink depth must equal (head diameter - bore diameter) / 2."
        )
    if width <= clearance.diameter + 0.2 or depth <= 0:
        raise ValueError("Fastener seat must be larger than the through bore.")
    return dict(
        width=width,
        depth=depth,
        radius=width / (math.sqrt(3) if choice.style == "nut_pocket" else 2),
        basis="Explicit dimensions" if choice.diameter else SOURCES[choice.style][0],
    )


def sites(a, r, plan):
    """Resolve centers from measured part features and the compiled base lands."""
    records = {c.feature_id: c for c in resolve_clearances(a, r)}
    i = selected_interface(a, r)
    result = []
    for op in plan.operations:
        if op.kind == "mount":
            for n in op.instance_ids:
                for hid in op.hole_ids:
                    center = (
                        np.array(i.centers[i.hole_ids.index(hid)]) + plan.placements[n]
                    )
                    result.append(
                        dict(
                            id=f"part-{n}-{hid}",
                            target=op.target,
                            axis="z",
                            center=center,
                            low=-r.thickness,
                            high=0.0,
                            entry="low",
                            choice=r.part_hardware,
                            clearance=records[hid],
                        )
                    )
    feet = {o.body: o for o in base_footprints(plan)}
    for op in plan.operations:
        if op.purpose != "Surrounding attachment bolt clearance":
            continue
        foot = feet[op.id.rsplit("-bench-", 1)[0]]
        k = "xyz".index(op.axis)
        result.append(
            dict(
                id=op.id,
                target=op.target,
                axis=op.axis,
                center=np.array(op.origin),
                low=foot.origin[k],
                high=foot.origin[k] + foot.size[k],
                entry="low" if r.base_hardware.style == "nut_pocket" else "high",
                choice=r.base_hardware,
                clearance=records["base"],
            )
        )
    if r.part_hardware.style != "none" and not i.hole_ids:
        raise ValueError("Part screw seats require selected mounting holes.")
    if r.base_hardware.style != "none" and r.surroundings != "bolt":
        raise ValueError("Base screw seats require bolted base attachment.")
    return result


def axial(site, low, high, diameter, shape="cylinder", end_diameter=None):
    axis = site["axis"]
    k = "xyz".index(axis)
    origin = np.array(site["center"], dtype=float)
    origin[k] = low
    profile = ()
    if shape == "prism":
        radius = diameter / math.sqrt(3)
        profile = tuple(
            (radius + radius * math.cos(t), radius + radius * math.sin(t))
            for t in np.linspace(0, 2 * math.pi, 6, endpoint=False)
        )
        if axis == "z":
            origin[:2] -= radius
        elif axis == "y":
            origin[0] -= radius
            origin[2] += radius
        else:
            origin[1] -= radius
            origin[2] += radius
        diameter = radius * 2
    return Operation(
        id="hardware-" + site["id"],
        kind="relief",
        target=site["target"],
        axis=axis,
        origin=tuple(origin),
        size=(diameter, end_diameter or diameter, high - low),
        shape=shape,
        profile=profile,
        purpose="Fastener accommodation",
        provenance={
            "center": "measured" if site["id"].startswith("part") else "derived",
            "style": "user",
            "dimensions": "derived",
        },
    )


def tooling(a, r, plan):
    result = []
    for site in sites(a, r, plan):
        choice = site["choice"]
        spec = specification(choice, site["clearance"])
        depth = spec["depth"]
        lo = site["low"]
        hi = site["high"]
        if depth > hi - lo - 1:
            raise ValueError(
                f"{site['id']}: fastener recess leaves less than 1 mm of stock. Increase thickness or choose shallower hardware."
            )
        low_entry = site["entry"] == "low"
        bottom, top = (lo, lo + depth) if low_entry else (hi - depth, hi)
        if depth:
            shape = {
                "counterbore": "cylinder",
                "countersink": "cone",
                "nut_pocket": "prism",
            }[choice.style]
            width = spec["width"]
            end = None
            if shape == "cone":
                # 90-degree frustum; bore and cone meet without changing measured centers.
                end = site["clearance"].diameter if low_entry else width
                width = width if low_entry else site["clearance"].diameter
            tool = axial(site, bottom, top, width, shape, end)
            result.append((site, spec, tool))
        if choice.driver_diameter:
            dl, dh = (
                (lo - choice.driver_reach, lo)
                if low_entry
                else (hi, hi + choice.driver_reach)
            )
            tool = axial(site, dl, dh, choice.driver_diameter).model_copy(
                update={
                    "id": "driver-" + site["id"],
                    "purpose": "Finite screwdriver access",
                }
            )
            result.append((site, spec, tool))
    return result


def add_hardware(a, r, plan):
    tools = tooling(a, r, plan)
    ops = list(plan.operations)
    for site, spec, tool in tools:
        targets = [site["target"]]
        if tool.id.startswith("driver-"):
            targets = sorted({o.body for o in ops if o.kind == "stock"})
        for target in targets:
            ops.append(
                tool.model_copy(
                    update={
                        "id": tool.id + "-" + target,
                        "target": target,
                        "depends_on": (ops[-1].id,),
                    }
                )
            )
    parameters = {
        **plan.parameters,
        "hardware_seats": sum(t.id.startswith("hardware-") for _, _, t in tools),
        "driver_envelopes": sum(t.id.startswith("driver-") for _, _, t in tools),
    }
    return Plan.model_validate(
        {**plan.model_dump(), "operations": ops, "parameters": parameters}
    )


def stem_range(choice, clearance, low, high, entry):
    d = specification(choice, clearance)["depth"]
    return (low + d, high) if entry == "low" else (low, high - d)


def validate_hardware(a, r, plan, bodies, add):
    import usd_brep as sm
    from .executor import primitive

    for site, spec, tool in tooling(a, r, plan):
        obstruction = sum(
            abs(
                sm.booleans.boolean_intersection(b.copy(), primitive(tool)).volume(
                    relative_accuracy=1e-8
                )
            )
            for b in bodies.values()
        )
        add(
            "Hardware clearance: " + tool.id,
            "Independent native seat/tool sweep from nominal or custom profile",
            obstruction,
            "passed" if obstruction < 0.01 else "failed",
            units="mm³",
            correction="Preserve the complete fastener seat and finite approach path.",
        )
        if tool.id.startswith("driver-"):
            continue
        # Require a 1 mm circular sidewall around the seat, including hex corners.
        rad = spec["radius"]
        k = "xyz".index(site["axis"])
        lo = tool.origin[k] + 0.01
        hi = lo + spec["depth"] - 0.02
        ring = sm.booleans.boolean_difference(
            primitive(axial(site, lo, hi, 2 * (rad + 1))),
            primitive(axial(site, lo, hi, 2 * rad)),
        )
        missing = abs(
            sm.booleans.boolean_difference(ring, bodies[site["target"]].copy()).volume(
                relative_accuracy=1e-8
            )
        )
        add(
            "Hardware web: " + tool.id,
            "Native full annular sidewall, 1 mm radial web; at least 1 mm axial floor required by compiler",
            missing,
            "passed" if missing < 0.01 else "failed",
            units="mm³",
            correction="Increase stock margin/spacing or reduce the recess dimensions.",
        )
        low, high = stem_range(
            site["choice"], site["clearance"], site["low"], site["high"], site["entry"]
        )
        low, high = (
            (low + 0.01, low + 0.99)
            if site["entry"] == "low"
            else (high - 0.99, high - 0.01)
        )
        floor = sm.booleans.boolean_difference(
            primitive(axial(site, low, high, 2 * rad)),
            primitive(axial(site, low, high, site["clearance"].diameter)),
        )
        missing = abs(
            sm.booleans.boolean_difference(floor, bodies[site["target"]].copy()).volume(
                relative_accuracy=1e-8
            )
        )
        add(
            "Hardware floor: " + tool.id,
            "Native full annular 1 mm floor beneath seat; bore excluded",
            missing,
            "passed" if missing < 0.01 else "failed",
            units="mm³",
            correction="Preserve the seat floor or increase stock thickness.",
        )


def hardware_record(a, r, plan):
    return {
        "verified": "2026-10-30",
        "sources": SOURCES,
        "fit_assumptions": "Head diameter +0.5 mm; nut flats +0.3 mm; cylindrical/nut depth +0.2 mm. Countersinks 90 degrees. Explicit overrides take priority.",
        "nut_retention": "Hex pockets prevent rotation. Base pockets are axially captured only when the mating base covers their opening; part pockets need an external cover/washer. No preload or thread strength calculation.",
        "seats": [
            {
                "id": s["id"],
                "style": s["choice"].style,
                **specification(s["choice"], s["clearance"]),
            }
            for s in sites(a, r, plan)
            if s["choice"].style != "none"
        ],
    }
