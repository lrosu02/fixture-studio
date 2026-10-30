"""Bounded rectangular locating trays, derived from the whole part envelope.

Walls do not follow arbitrary contours. A strap is external hardware, not a
generated or strength-validated component. OCCT never constructs these fixtures.
"""

import numpy as np
from .contracts import Operation, MM_TOL


def tray_dimensions(r, lo, hi):
    if lo[2] < -MM_TOL:
        raise ValueError(
            "A locating tray needs an outer support face with the whole part above it. Select another face."
        )
    if min(hi - lo) <= MM_TOL:
        raise ValueError(
            "The selected part has no finite envelope for a locating tray."
        )
    height = r.locating_height or min(5.0, float(hi[2]) / 2)
    extension = r.locating_clearance + r.locating_wall
    if r.part_attachment == "strap":
        if not r.strap_width or not r.strap_thickness:
            raise ValueError(
                "Specify the external strap width and thickness before generating its slots."
            )
        if r.strap_width + 1 > hi[1] - lo[1] or height >= hi[2] - MM_TOL:
            raise ValueError(
                "The strap must fit across the part and above the locating walls. Reduce strap width or wall height, or select another face."
            )
        extension += r.strap_thickness + 5  # slot thickness + 1 fit + two 2 mm lands
    return float(extension), float(height)


def tray_operations(r, lo, hi, placements, target, previous):
    _, height = tray_dimensions(r, lo, hi)
    clearance, wall = r.locating_clearance, r.locating_wall
    ops = []
    for n, p in enumerate(placements):
        low, high = lo + p, hi + p
        x0, y0 = low[:2] - clearance
        x1, y1 = high[:2] + clearance
        rectangles = (
            (x0 - wall, y0 - wall, wall, y1 - y0 + 2 * wall),
            (x1, y0 - wall, wall, y1 - y0 + 2 * wall),
            (x0, y0 - wall, x1 - x0, wall),
            (x0, y1, x1 - x0, wall),
        )
        for side, (x, y, dx, dy) in enumerate(rectangles):
            name = f"locating-wall-{n}-{side}"
            ops.append(
                Operation(
                    id=name,
                    kind="support",
                    body=name,
                    target=target,
                    depends_on=(previous,),
                    origin=(x, y, -min(0.2, r.thickness / 2)),
                    size=(dx, dy, height + min(0.2, r.thickness / 2)),
                    purpose="Rectangular locating wall outside measured part envelope",
                    provenance={
                        "position": "derived",
                        "part_envelope": "measured",
                        "clearance": r.provenance.get("locating_clearance", "assumed"),
                        "wall": r.provenance.get("locating_wall", "assumed"),
                    },
                )
            )
            previous = name + "-join"
            ops.append(
                Operation(
                    id=previous,
                    kind="combine",
                    target=target,
                    other=name,
                    depends_on=(name,),
                    purpose="Join locating wall to tray base",
                    provenance={"connection": "derived"},
                )
            )
        if r.part_attachment == "strap":
            slot_x = r.strap_thickness + 1
            slot_y = r.strap_width + 1
            for side, x in enumerate((x0 - wall - 2 - slot_x, x1 + wall + 2)):
                name = f"strap-slot-{n}-{side}"
                ops.append(
                    Operation(
                        id=name,
                        kind="relief",
                        target=target,
                        depends_on=(previous,),
                        origin=(x, (y0 + y1 - slot_y) / 2, -r.thickness - 1),
                        size=(slot_x, slot_y, r.thickness + 2),
                        purpose="Through slot for external retaining strap",
                        provenance={
                            "strap_dimensions": "user",
                            "slot_fit_allowance": "assumed",
                            "position": "derived",
                        },
                    )
                )
                previous = name
    return ops


def validate_tray(a, r, plan, bodies, add):
    import usd_brep as sm
    from .executor import primitive
    from .intake import selected_interface, local_points
    from .face_picking import face_surface

    i = selected_interface(a, r)
    pts = local_points(a.mesh.vertices, i)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    required = tray_operations(r, lo, hi, plan.placements, "stock-0", "stock-0")
    wall_error, slot_obstruction, collisions = 0.0, 0.0, 0.0
    for p in plan.placements:
        # This box encloses the measured source. Boundary contact at z=0 is intentional.
        probe = sm.primitives.create_box(
            tuple(lo + p + np.array([0, 0, MM_TOL])),
            *tuple(hi - lo - np.array([0, 0, MM_TOL])),
        )
        collisions += sum(
            abs(sm.booleans.boolean_intersection(b.copy(), probe.copy()).volume())
            for b in bodies.values()
        )
    for op in required:
        if op.kind not in ("support", "relief"):
            continue
        probe = primitive(op)
        occupied = sum(
            abs(sm.booleans.boolean_intersection(b.copy(), probe.copy()).volume())
            for b in bodies.values()
        )
        if op.kind == "support":
            wall_error = max(wall_error, abs(occupied - probe.volume()))
        else:
            slot_obstruction += occupied
    add(
        "Locating walls",
        "Native volume coverage of four independently derived walls per part",
        wall_error,
        "passed" if wall_error < 0.01 else "failed",
        units="mm³",
    )
    add(
        "Part envelope clearance",
        "Native intersection with the measured whole-part bounding box above its support plane",
        collisions,
        "passed" if collisions < 0.01 else "failed",
        units="mm³",
    )
    patch = face_surface(a, i)
    triangles = np.asarray(patch.triangles)
    if not len(triangles):
        raise ValueError(
            "No measured trimmed support patch available; reimport the STEP."
        )
    centers = np.asarray(patch.vertices)[
        triangles[
            np.linspace(0, len(triangles) - 1, min(32, len(triangles))).astype(int)
        ]
    ].mean(axis=1)
    centers = local_points(centers, i)
    error = max(
        min(sm.get_closest_point(b, tuple(c + p))[1] for b in bodies.values())
        for p in plan.placements
        for c in centers
    )
    add(
        "Face support",
        "Native closest-point checks at up to 32 measured trimmed-face triangle centroids per part",
        error,
        "passed" if error < MM_TOL else "failed",
    )
    if r.part_attachment == "strap":
        add(
            "Strap passages",
            "Native intersection with both independently derived full-depth strap slots per part",
            slot_obstruction,
            "passed" if slot_obstruction < 0.01 else "failed",
            units="mm³",
        )
    add(
        "Part retention",
        "Tray walls locate laterally; strap hardware/tension and load capacity are not modeled"
        if r.part_attachment == "strap"
        else "Open tray provides no hold-down; requires a supported resting orientation",
        r.part_attachment,
        "not_evaluated",
        units="relationship",
    )
