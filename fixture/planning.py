"""Deterministic compiler: decisions and measured references -> bounded operations."""

import numpy as np
from .contracts import (
    Operation,
    Plan,
    Proposal,
    Requirements,
    PrintSettings,
    HoleFastenerChoice,
    MM_TOL,
    MAX_OPS,
)
from .intake import local_points, selected_interface
from .structures import STRUCTURES, compile_structure
from .fasteners import resolve_clearances
from .base_mounting import distribute_count, two_lanes
from .clearance import fixture_regions, footprint_distance


def patch_requirements(current, changes, origin="user"):
    changes = dict(changes)
    if changes.get("part_attachment", current.part_attachment) != "screws":
        changes.setdefault("mounting_hole_ids", ())
        changes.setdefault("hole_fasteners", ())
    if changes.get("interface_id", current.interface_id) != current.interface_id:
        changes.setdefault("rear_passages", ())
        changes.setdefault("hole_fasteners", ())
        changes.setdefault("access_selections", ())
    elif "mounting_hole_ids" in changes and "hole_fasteners" not in changes:
        selected = set(changes["mounting_hole_ids"])
        changes["hole_fasteners"] = tuple(
            c.model_copy(
                update={"hole_ids": tuple(h for h in c.hole_ids if h in selected)}
            )
            for c in current.hole_fasteners
            if selected.intersection(c.hole_ids)
        )
    if "print_settings" in changes:
        changes["print_settings"] = PrintSettings.model_validate(
            changes["print_settings"]
        )
    if "hole_fasteners" in changes:
        choices = tuple(
            HoleFastenerChoice.model_validate(v) for v in changes["hole_fasteners"]
        )
        before = {h: c for c in current.hole_fasteners for h in c.hole_ids}
        after = {h: c for c in choices for h in c.hole_ids}
        for h in set(before) | set(after):
            old, new = before.get(h), after.get(h)
            if "nominal_fastener" in current.locks and (
                old.nominal if old else current.nominal_fastener
            ) != (new.nominal if new else current.nominal_fastener):
                raise ValueError(
                    "nominal_fastener is locked; unlock it before changing hole screw sizes."
                )
            if "clearance_diameter" in current.locks and (
                old.clearance_diameter
                if old and old.clearance_diameter is not None
                else current.clearance_diameter
            ) != (
                new.clearance_diameter
                if new and new.clearance_diameter is not None
                else current.clearance_diameter
            ):
                raise ValueError(
                    "clearance_diameter is locked; unlock it before overriding a hole clearance."
                )
        changes["hole_fasteners"] = choices
    for key, value in changes.items():
        if key in current.locks and value != getattr(current, key):
            raise ValueError(
                f"{key} is locked at {getattr(current, key)}. Unlock it explicitly before changing it."
            )
    data = current.model_dump()
    data.update(changes)
    data["provenance"] = {**current.provenance, **{k: origin for k in changes}}
    if "print_settings" in changes:
        data["provenance"].update(
            {
                "print_settings." + k: origin
                for k, v in changes["print_settings"].model_dump().items()
                if v != getattr(current.print_settings, k)
            }
        )
    return Requirements.model_validate(data)


def missing_questions(a, r, automatic_clearance=True):
    questions = []
    if not r.purpose:
        questions.append("What operation should this fixture support?")
    if r.quantity is None:
        questions.append(
            "How many parts should it hold, and is footprint or individual access more important?"
        )
    if not r.interface_id or not r.mounting_confirmed:
        questions.append(
            "Select and confirm the surface that should contact the fixture. Select fastener holes only if the part will be screwed down."
        )
    interface = next((i for i in a.interfaces if i.id == r.interface_id), None)
    if r.part_attachment == "unselected" or (
        interface and not interface.hole_ids and r.part_attachment == "screws"
    ):
        questions.append(
            "How should the part be retained: resting in a locating tray, or held with an external strap through tray slots?"
        )
    if r.part_attachment == "strap" and (not r.strap_width or not r.strap_thickness):
        questions.append(
            "What are the width and thickness of the retaining strap (mm), and may it cross over the part?"
        )
    if (
        r.part_attachment != "screws"
        and r.surroundings == "bolt"
        and not (r.bench_fastener or r.bench_hole_diameter)
    ):
        questions.append("What screw size should attach the tray to its base?")
    if not automatic_clearance and r.clearance_diameter is None:
        questions.append(
            "What fixture clearance-hole diameter should be used (mm)? Nominal thread and engagement may remain unknown."
        )
    if r.motion_loads is None:
        questions.append(
            "Will anything move or rotate, what is attached, and what space must remain clear? Unknown is accepted for a concept."
        )
    if r.surroundings == "unknown":
        questions.append("Will the fixture be clamped or bolted to its surroundings?")
    if (
        not automatic_clearance
        and r.surroundings == "bolt"
        and not r.bench_hole_diameter
    ):
        questions.append(
            "What clearance diameter should the bench attachment holes use?"
        )
    if r.fabrication is None:
        questions.append(
            "Which manufacturing method should the design use, and are thickness constraints known?"
        )
    if r.access is None:
        questions.append(
            "Which ports, cables, tools or surfaces need access? Give finite clearance dimensions when known."
        )
    if r.through_access_required and not r.rear_passages:
        questions.append(
            "Choose the measured rear recess for the requested through wire/tool opening; a blind relief does not satisfy through access."
        )
    if not r.assumptions_accepted:
        questions.append(
            "Review and accept the visible concept assumptions, or replace the defaults."
        )
    return questions[:3]


def proposals(a, r):
    if not r.interface_id:
        return ()
    unresolved = tuple(r.unknowns) + tuple(r.assumptions)
    result = []

    def add(composition, suffix="", title=None, rationale=None, **variant):
        try:
            candidate = patch_requirements(r, dict(composition=composition, **variant))
            plan = compile_plan(a, candidate, require_ready=False)
        except ValueError:
            return None
        result.append(
            Proposal(
                id=composition + suffix,
                interface_id=r.interface_id,
                composition=composition,
                title=title
                or (
                    {"cradle": "Locating tray", "strap": "Strap-retained tray"}.get(
                        r.part_attachment
                    )
                    or STRUCTURES[composition][0]
                ),
                rationale=rationale
                or (
                    {
                        "cradle": "Measured rectangular locating walls; open above, with no hold-down.",
                        "strap": "Measured locating walls and through slots for your external strap.",
                    }.get(r.part_attachment)
                    or STRUCTURES[composition][1]
                ),
                surroundings="Extended end lands for clamps."
                if r.surroundings != "bolt"
                else "Clearance holes in the base attachment lands; the mating base pattern must match these generated positions.",
                unresolved=unresolved,
                checks=(
                    "alignment",
                    "dimensions",
                    "contact samples",
                    "envelopes",
                    "topology",
                    "export",
                ),
                dimensions=plan.parameters,
                **variant,
            )
        )
        return plan

    for composition in STRUCTURES:
        base = add(composition)
        if base is None or composition not in ("l_bracket", "bridge"):
            continue
        if composition == "l_bracket":
            add(
                composition,
                "-ribs",
                "Open L-bracket" if r.reinforce else "Ribbed L-bracket",
                "No side ribs; more room behind the wall."
                if r.reinforce
                else "Side ribs support the wall-to-foot corner.",
                reinforce=not r.reinforce,
            )
        if r.mount_height is None:
            add(
                composition,
                "-raised",
                "Raised L-bracket" if composition == "l_bracket" else "Raised bridge",
                "More space above the base; greater overall height.",
                mount_height=float(base.parameters["mount_height_mm"])
                + 2 * r.thickness,
            )
    return tuple(sorted(result, key=lambda p: p.composition != r.composition))


def proposal_requirements(requirements, proposal):
    changes = {"composition": proposal.composition}
    for field in ("reinforce", "mount_height"):
        value = getattr(proposal, field)
        if value is not None:
            changes[field] = value
    return patch_requirements(requirements, changes)


def compile_plan(a, r, require_ready=True, compiler_version=9):
    if compiler_version < 9:
        if r.access_selections:
            raise ValueError('Selected access needs compiler version 9.')
        return _compile_plan(a, r, require_ready, compiler_version)
    if compiler_version != 9:
        raise ValueError('Unsupported compiler version.')
    from .access import add_access
    plan = _compile_plan(a, r, require_ready, 8)
    plan = plan.model_copy(update={'version':9})
    return add_access(a, r, plan)


def _compile_plan(a, r, require_ready=True, compiler_version=8):
    if compiler_version not in (1, 2, 3, 4, 5, 6, 7, 8):
        raise ValueError("Unsupported compiler version.")
    if r.bench_hole_count is not None and r.bench_hole_count > MAX_OPS:
        raise ValueError(
            f"The requested base holes exceed the {MAX_OPS}-operation CAD budget; split this design into smaller fixtures."
        )
    if r.bench_hole_count is not None and compiler_version < 5:
        raise ValueError("Explicit base hole counts require compiler version 5.")
    if r.bench_hole_count is not None and r.surroundings != "bolt":
        raise ValueError(
            "A base hole count requires bolted attachment to surroundings."
        )
    if r.through_access_required and not r.rear_passages:
        raise ValueError(
            "Select the measured rear recess for the required through wire/tool opening before generating."
        )
    if r.rear_passages and (
        compiler_version < 4
        or (
            r.composition not in ("l_bracket", "bridge")
            and not (compiler_version >= 7 and r.composition == "plate")
        )
    ):
        raise ValueError(
            "Measured rear through passages require an L-bracket/bridge (version 4+) or a mounting plate (version 7+)."
        )
    questions = missing_questions(a, r, automatic_clearance=compiler_version >= 3)
    if require_ready and questions:
        raise ValueError(
            "Resolve the next questions before generating: " + " ".join(questions)
        )
    if r.fabrication and any(
        w in r.fabrication.lower()
        for w in ("sheet metal", "unfold", "casting", "cast ")
    ):
        raise ValueError(
            "This executor supports solid stock, machining concepts or printing concepts. Select a supported route; unfolding and casting are not implemented."
        )
    i = selected_interface(a, r)
    if r.part_attachment == "unselected" or (
        r.part_attachment == "screws" and not i.hole_ids
    ):
        raise ValueError(
            "Choose how to retain this part; this face has no selected screw holes."
        )
    nonbolted = r.part_attachment in ("cradle", "strap")
    if nonbolted and (compiler_version < 8 or r.composition != "plate"):
        raise ValueError(
            "Hole-free locating/strap trays currently require a plate and compiler version 8."
        )
    clearances = resolve_clearances(a, r) if compiler_version >= 3 else ()
    by_hole = {c.feature_id: c for c in clearances}
    if "base" in by_hole:
        r = r.model_copy(
            update={
                "bench_hole_diameter": by_hole["base"].diameter,
                "provenance": {
                    **r.provenance,
                    "bench_hole_diameter": by_hole["base"].origin,
                },
            }
        )
    if not i.contact_ok:
        raise ValueError(
            "Sampled contact patches do not fit this face. Choose another candidate or revise the source; hole alignment alone is insufficient."
        )
    pts = local_points(a.mesh.vertices, i)
    if pts[:, 2].min() < -MM_TOL and (
        r.composition == "rails" or (r.composition == "plate" and compiler_version < 7)
    ):
        raise ValueError(
            "Source protrudes behind the attachment plane. Select an outer mounting face or a structure with measured rear relief. Plates require compiler version 7; rails do not support that relief."
        )
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    extension = 0.0
    if nonbolted:
        from .retention import tray_dimensions

        extension, _ = tray_dimensions(r, lo, hi)
    qty = r.quantity or 1
    cols = qty if r.layout == "row" else min(qty, r.columns)
    pitch = (hi - lo)[:2] + r.gap + 2 * extension
    placements = np.array(
        [(n % cols * pitch[0], n // cols * pitch[1], 0.0) for n in range(qty)]
    )
    placements[:, :2] -= (
        placements[:, :2].max(axis=0) + placements[:, :2].min(axis=0)
    ) / 2
    diameter = (
        max(c.diameter for c in clearances if c.feature_id != "base")
        if i.hole_ids and clearances
        else (r.clearance_diameter or min(i.diameters))
        if i.hole_ids
        else 0.0
    )
    # Source diameter remains separate; enlarged fixture bores must preserve
    # at least 1 mm to the sampled contact radius.
    allowed_diameter = (
        min(i.diameters)
        if compiler_version < 3 and r.composition in ("plate", "rails")
        else 2 * (min(i.contact_radii) - 1)
        if i.hole_ids
        else 0.0
    )
    oversized = (
        any(
            by_hole[h].diameter > 2 * (radius - 1) + MM_TOL
            for h, radius in zip(i.hole_ids, i.contact_radii)
        )
        if clearances
        else diameter > allowed_diameter + MM_TOL
    )
    if oversized:
        raise ValueError(
            "Clearance would leave less than 1 mm of sampled contact support. Choose another interface or revise the fastener/clearance."
            if compiler_version >= 3
            else "Clearance diameter exceeds a measured opening. Confirm a suitable interface or use a smaller clearance; thread size is not inferred."
        )
    start = np.min(placements[:, :2] + lo[:2], axis=0) - r.margin - extension
    end = np.max(placements[:, :2] + hi[:2], axis=0) + r.margin + extension
    width = float(end[0] - start[0])
    if r.max_width and width > r.max_width + MM_TOL:
        raise ValueError(
            f"Required width {width:.2f} mm exceeds max_width {r.max_width:.2f} mm. Change quantity, layout, gap, margin or the width limit; measured holes cannot move."
        )
    hole_specs = [
        (n, hid, np.array(c) + p, rad)
        for n, p in enumerate(placements)
        for hid, c, rad in zip(i.hole_ids, i.centers, i.contact_radii)
    ]
    if r.composition in ("l_bracket", "bridge"):
        return compile_structure(
            a,
            r,
            i,
            pts,
            placements,
            start,
            end,
            hole_specs,
            diameter,
            compiler_version,
            clearances,
        )
    bands = []
    if r.composition == "plate":
        bands = [(start[1], end[1], hole_specs)]
    else:
        # Union overlapping support strips. Works for arbitrary numbers and rows.
        for spec in sorted(hole_specs, key=lambda h: h[2][1]):
            y = spec[2][1]
            half = max(
                spec[3] + 1,
                (by_hole[spec[1]].diameter if clearances else diameter) / 2 + 2,
            )
            if bands and y - half <= bands[-1][1] + MM_TOL:
                low, high, group = bands[-1]
                bands[-1] = (low, max(high, y + half), group + [spec])
            else:
                bands.append((y - half, y + half, [spec]))
        if len(bands) < 2:
            raise ValueError(
                "This pattern has no usable gap between support rows. The common plate is supported."
            )
    ops = [
        Operation(
            id="place",
            kind="place",
            interface_id=i.id,
            instance_ids=tuple(range(qty)),
            purpose="Align source instances with measured interface",
            provenance={
                "positions": "derived",
                "quantity": r.provenance.get("quantity", "user"),
            },
        )
    ]
    enhanced = ()
    for b, (y0, y1, holes) in enumerate(bands):
        name = f"stock-{b}"
        ops.append(
            Operation(
                id=name,
                kind="stock",
                body=name,
                depends_on=("place",),
                origin=(start[0], y0, -r.thickness),
                size=(width, y1 - y0, r.thickness),
                purpose=r.composition,
                provenance={
                    "size": "derived",
                    "thickness": r.provenance.get("thickness", "assumed"),
                },
            )
        )
        previous = name
        if nonbolted:
            from .retention import tray_operations

            additions = tray_operations(r, lo, hi, placements, name, previous)
            ops.extend(additions)
            previous = additions[-1].id
        if compiler_version >= 7 and r.composition == "plate":
            enhanced = fixture_regions(a, i, r, placements, ops)
            for region in enhanced:
                if region.origin[2] <= 0 <= region.origin[2] + region.size[2]:
                    if any(
                        footprint_distance(region, center) < radius + 0.3
                        for _, _, center, radius in holes
                    ):
                        raise ValueError(
                            "Measured rear clearance overlaps a selected mounting contact. Choose another mounting face or revise clearance; no holes were moved."
                        )
                ops.append(
                    region.model_copy(
                        update={"target": name, "depends_on": (previous,)}
                    )
                )
                previous = region.id
        for n, hid, c, rad in holes:
            oid = f"{name}-mount-{n}-{hid}"
            ops.append(
                Operation(
                    id=oid,
                    kind="mount",
                    target=name,
                    depends_on=(previous,),
                    interface_id=i.id,
                    instance_ids=(n,),
                    hole_ids=(hid,),
                    diameter=by_hole[hid].diameter if clearances else diameter,
                    origin=(0, 0, -r.thickness - 1),
                    size=(1, 1, r.thickness + 2),
                    purpose="Measured part fastener clearance",
                    provenance={
                        "pattern": "measured",
                        "diameter": by_hole[hid].origin
                        if clearances
                        else r.provenance.get("clearance_diameter", "user"),
                    },
                )
            )
            previous = oid
        if r.surroundings == "bolt":
            if not r.bench_hole_diameter:
                raise ValueError("Specify bench hole diameter.")
            if r.margin < r.bench_hole_diameter + 2:
                raise ValueError("Increase margin for bench-hole edge distance.")
            positions = [
                (x, (y0 + y1) / 2)
                for x in (start[0] + r.margin / 2, end[0] - r.margin / 2)
            ]
            if r.bench_hole_count is not None:
                count = distribute_count(r.bench_hole_count, len(bands))[b]
                inset = r.bench_hole_diameter / 2 + 2
                positions = two_lanes(
                    start[0] + r.margin / 2,
                    end[0] - r.margin / 2,
                    y0 + inset,
                    y1 - inset,
                    count,
                    r.bench_hole_diameter,
                )
                if count == 1:
                    positions = [(start[0] + r.margin / 2, (y0 + y1) / 2)]
            for side, (x, y) in enumerate(positions):
                oid = f"{name}-bench-{side}"
                ops.append(
                    Operation(
                        id=oid,
                        kind="relief",
                        target=name,
                        shape="cylinder",
                        depends_on=(previous,),
                        origin=(x, y, -r.thickness - 1),
                        size=(
                            r.bench_hole_diameter,
                            r.bench_hole_diameter,
                            r.thickness + 2,
                        ),
                        purpose="Surrounding attachment bolt clearance",
                        provenance={
                            "diameter": by_hole["base"].origin
                            if clearances
                            else "user",
                            "position": "derived",
                        },
                    )
                )
                previous = oid
        for n, p in enumerate(placements):
            for env in r.envelopes:
                elo = np.array(env.minimum) + p
                ehi = np.array(env.maximum) + p
                if (
                    elo[2] < 0
                    and ehi[2] > -r.thickness
                    and np.all(ehi[:2] > [start[0], y0])
                    and np.all(elo[:2] < [end[0], y1])
                ):
                    # Do not remove any measured contact footprint.
                    for _, hid, c, rad in holes:
                        nearest = np.clip(c[:2], elo[:2], ehi[:2])
                        if np.linalg.norm(c[:2] - nearest) < rad + 1:
                            raise ValueError(
                                f"Access region {env.id} conflicts with contact around {hid}. Move or resize that region."
                            )
                    oid = f"{name}-access-{n}-{env.id}"
                    ops.append(
                        Operation(
                            id=oid,
                            kind="relief",
                            target=name,
                            depends_on=(previous,),
                            origin=tuple(elo),
                            size=tuple(ehi - elo),
                            purpose=env.purpose,
                            provenance={"region": "user"},
                        )
                    )
                    previous = oid
    return Plan(
        version=compiler_version if compiler_version >= 3 else 1,
        clearances=clearances,
        source_hash=a.source_hash,
        interface_id=i.id,
        composition=r.composition,
        placements=tuple(tuple(p) for p in placements),
        operations=tuple(ops),
        parameters={
            "width_mm": width,
            "depth_mm": float(end[1] - start[1]),
            "thickness_mm": r.thickness,
            "gap_mm": r.gap,
            "clearance_diameter_mm": diameter,
            "quantity": qty,
            **(
                {
                    "part_attachment": r.part_attachment,
                    "locating_clearance_mm": r.locating_clearance,
                    "locating_wall_mm": r.locating_wall,
                    "locating_height_mm": tray_dimensions(r, lo, hi)[1],
                    "envelope_expansion_mm": extension,
                }
                if nonbolted
                else {}
            ),
            **(
                {
                    "rear_region_count": len(enhanced),
                    "rear_passage_count": len(r.rear_passages) * qty,
                    "rear_clearance_mm": r.rear_clearance,
                }
                if compiler_version >= 7 and r.composition == "plate"
                else {}
            ),
            **(
                {
                    "base_hole_count": sum(
                        op.purpose == "Surrounding attachment bolt clearance"
                        for op in ops
                    )
                }
                if compiler_version >= 5
                else {}
            ),
        },
    )
