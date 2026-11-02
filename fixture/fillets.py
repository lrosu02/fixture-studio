"""Bounded SMLib fillets on the two inward, straight L-bracket rib/base roots."""

import numpy as np
import usd_brep as sm

from .contracts import Operation, Plan


def root_segments(plan):
    ribs = sorted(
        (
            o
            for o in plan.operations
            if o.kind == "support" and o.id.startswith("corner-rib-")
        ),
        key=lambda o: o.origin[0],
    )
    foot = next((o for o in plan.operations if o.id == "base-foot"), None)
    wall = next((o for o in plan.operations if o.id == "mounting-platform"), None)
    if len(ribs) != 2 or not foot or not wall:
        return ()
    y = foot.origin[1] + foot.size[1]
    result = []
    for n, rib in enumerate(ribs):
        x = rib.origin[0] + (rib.size[0] if n == 0 else 0)
        z = rib.origin[2] + (y - rib.origin[1]) * rib.size[2] / rib.size[1]
        result.append(((x, y, z), (x, y, wall.origin[2])))
    return tuple(result)


def add_rib_fillets(r, plan):
    from .manufacturing import is_sheet_metal

    if is_sheet_metal(r.fabrication):
        return plan
    if plan.composition != "l_bracket" or not r.reinforce or not r.auto_rib_fillets:
        return plan
    segments = root_segments(plan)
    if not segments:
        return plan
    limit = min(
        2.0,
        r.thickness / 2,
        (segments[1][0][0] - segments[0][0][0]) / 8,
        *((b[2] - a[2]) / 8 for a, b in segments),
    )
    radius = r.rib_fillet_radius or min(limit, 1.5, r.thickness / 4)
    if limit <= 0 or radius > limit:
        raise ValueError(
            f"Rib fillet radius must be at most {max(0, limit):.3f} mm for this bracket."
        )
    op = Operation(
        id="rib-root-fillets",
        kind="fillet",
        target="mounting-platform",
        edge_segments=segments,
        fillet_radius=radius,
        purpose="Round inward rib-to-base joints",
        provenance={
            "edges": "derived",
            "radius": "user" if r.rib_fillet_radius else "assumed",
        },
    )
    ops = list(plan.operations)
    index = max(n for n, o in enumerate(ops) if o.id.startswith("join-corner-rib-")) + 1
    ops.insert(index, op)
    # Finish roots before access/hardware cuts; those cuts retain full priority.
    ops = [
        o.model_copy(update={"depends_on": (ops[n - 1].id,) if n else ()})
        for n, o in enumerate(ops)
    ]
    return Plan.model_validate(
        {
            **plan.model_dump(),
            "operations": ops,
            "parameters": {
                **plan.parameters,
                "rib_fillet_radius_mm": radius,
                "rib_fillet_count": len(segments),
            },
        }
    )


def apply_fillet(body, op):
    edges = []
    for start, end in op.edge_segments:
        wanted = sorted((start, end), key=lambda p: p[2])
        matches = []
        for edge in body.edges():
            actual = sorted(
                (edge.start_vertex().point(), edge.end_vertex().point()),
                key=lambda p: p[2],
            )
            if (
                np.allclose(actual, wanted, atol=1e-5, rtol=0)
                and abs(edge.length() - np.linalg.norm(np.subtract(end, start))) < 1e-5
            ):
                matches.append(edge)
        if len(matches) != 1:
            raise ValueError(
                "Cannot identify a unique rib/base edge; disable automatic rib fillets or revise the bracket."
            )
        edges.extend(matches)
    old_volume = body.volume(relative_accuracy=1e-8)
    # Native filleting may mutate the supplied BRep. Resolve all handles from it,
    # never use stale indices or handles from a copied or previous body.
    result = sm.fillets.fillet_edges(body, edges, radius=op.fillet_radius)
    if (
        not result.is_manifold_solid()
        or result.material_census()["solid_count"] != 1
        or result.volume(relative_accuracy=1e-8) <= old_volume
    ):
        raise ValueError("Rib fillets did not produce a connected rounded joint.")
    return result


def validate_fillets(r, plan, bodies, add):
    expected = add_rib_fillets(
        r,
        plan.model_copy(
            update={
                "operations": tuple(o for o in plan.operations if o.kind != "fillet")
            }
        ),
    )
    ops = [o for o in expected.operations if o.kind == "fillet"]
    if not ops:
        return
    from .executor import primitive

    for op in ops:
        radius = op.fillet_radius
        for n, (start, end) in enumerate(op.edge_segments):
            checked, failed = 0, False
            for fraction in (0.25, 0.5, 0.75):
                z = start[2] + (end[2] - start[2]) * fraction
                for offset, material in ((0.12, True), (0.6, False)):
                    epsilon = radius * 0.02
                    center = (
                        start[0] + (1 if n == 0 else -1) * radius * offset,
                        start[1] + radius * offset,
                        z,
                    )
                    probe = sm.primitives.create_box(
                        tuple(v - epsilon / 2 for v in center),
                        epsilon,
                        epsilon,
                        epsilon,
                    )
                    # An explicitly requested passage can legitimately cut a root.
                    if any(
                        abs(
                            sm.booleans.boolean_intersection(
                                probe.copy(), primitive(cut)
                            ).volume(relative_accuracy=1e-8)
                        )
                        > epsilon**3 * 0.01
                        for cut in plan.operations
                        if cut.kind == "relief"
                    ):
                        continue
                    volume = abs(
                        sm.booleans.boolean_intersection(
                            bodies[op.target].copy(), probe
                        ).volume(relative_accuracy=1e-8)
                    )
                    failed |= abs(volume / epsilon**3 - int(material)) > 0.02
                    checked += 1
            add(
                f"Rib root fillet {n + 1}",
                "Native material/void samples across the expected circular root; requested reliefs excluded",
                f"R{radius:g} mm; {checked} samples",
                "failed" if failed else "passed" if checked == 6 else "inconclusive",
                correction="Restore the rounded root or revise interfering access cuts.",
            )
