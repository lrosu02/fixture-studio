"""All fixture BReps are constructed here, exclusively in NVIDIA SMLib."""

from pathlib import Path
import threading
import numpy as np
import usd_brep as sm
from .contracts import Mesh, Plan, MM_TOL
from .intake import get_interface
from .cad_io import export_verified

KERNEL_LOCK = threading.RLock()


def primitive(op):
    x, y, z = op.origin
    a, b, c = op.size
    if op.shape == "bend_relief":
        center = (x, y + b, z)
        keep = sm.primitives.create_cylinder(center, op.bend_radius, a)
        keep = sm.transforms.rotate(keep, center, (0.0, 1.0, 0.0), 90.0)
        return sm.booleans.boolean_difference(
            sm.primitives.create_box((x, y, z), a, b, c), keep
        )
    if op.shape == "quarter_bend":
        center = (x, y + b, z)
        outer = sm.primitives.create_cylinder(center, b, a)
        inner = sm.primitives.create_cylinder(center, op.bend_radius, a)
        outer = sm.transforms.rotate(outer, center, (0.0, 1.0, 0.0), 90.0)
        inner = sm.transforms.rotate(inner, center, (0.0, 1.0, 0.0), 90.0)
        ring = sm.booleans.boolean_difference(outer, inner)
        return sm.booleans.boolean_intersection(
            ring, sm.primitives.create_box((x, y, z), a, b, c)
        )
    if op.shape == "box":
        return sm.primitives.create_box((x, y, z), a, b, c)
    if op.shape in ("rounded_box", "chamfer_box"):
        radius = op.corner_radius
        width, depth, height = (a, c, b) if op.axis == "y" else (a, b, c)
        if op.axis not in ("y", "z"):
            raise ValueError("Finished stock needs a Y or Z normal.")
        if op.shape == "rounded_box":
            body = sm.primitives.create_box(
                (radius, 0, 0), width - 2 * radius, depth, height
            )
            body = sm.booleans.boolean_union(
                body,
                sm.primitives.create_box(
                    (0, radius, 0), width, depth - 2 * radius, height
                ),
            )
            for cx in (radius, width - radius):
                for cy in (radius, depth - radius):
                    body = sm.booleans.boolean_union(
                        body, sm.primitives.create_cylinder((cx, cy, 0), radius, height)
                    )
        else:
            points = [
                (radius, 0, 0),
                (width - radius, 0, 0),
                (width, radius, 0),
                (width, depth - radius, 0),
                (width - radius, depth, 0),
                (radius, depth, 0),
                (0, depth - radius, 0),
                (0, radius, 0),
            ]
            curves = [
                sm.curves.create_line_segment(points[n], points[(n + 1) % 8])
                for n in range(8)
            ]
            body = sm.sweeps.linear_sweep(
                curves, (0.0, 0.0, 1.0), height, cap_ends=True
            )
        if op.axis == "y":
            body = sm.transforms.rotate(body, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), -90.0)
            z += depth
        return sm.transforms.translate(body, (x, y, z))
    if op.shape in ("cylinder", "cone"):
        body = (
            sm.primitives.create_cylinder((x, y, z), a / 2, c)
            if op.shape == "cylinder"
            else sm.primitives.create_cone((x, y, z), a / 2, b / 2, c)
        )
        if op.axis != "z":
            body = sm.transforms.rotate(
                body,
                (x, y, z),
                (1.0, 0.0, 0.0) if op.axis == "y" else (0.0, 1.0, 0.0),
                -90.0 if op.axis == "y" else 90.0,
            )
        return body
    if op.shape == "wedge":
        points = [(x, y, z), (x, y + b, z + c), (x, y, z + c)]
        curves = [
            sm.curves.create_line_segment(points[n], points[(n + 1) % 3])
            for n in range(3)
        ]
        return sm.sweeps.linear_sweep(curves, (1.0, 0.0, 0.0), a, cap_ends=True)
    if op.shape == "prism":
        points = [(x + u, y + v, z) for u, v in op.profile]
        curves = [
            sm.curves.create_line_segment(points[n], points[(n + 1) % len(points)])
            for n in range(len(points))
        ]
        body = sm.sweeps.linear_sweep(curves, (0.0, 0.0, 1.0), c, cap_ends=True)
        if op.axis != "z":
            body = sm.transforms.rotate(
                body,
                (x, y, z),
                (1.0, 0.0, 0.0) if op.axis == "y" else (0.0, 1.0, 0.0),
                -90.0 if op.axis == "y" else 90.0,
            )
        return body
    if a <= b:
        raise ValueError("Slot length must exceed its diameter.")
    box = sm.primitives.create_box((x + b / 2, y, z), a - b, b, c)
    for cx in (x + b / 2, x + a - b / 2):
        box = sm.booleans.boolean_union(
            box, sm.primitives.create_cylinder((cx, y + b / 2, z), b / 2, c)
        )
    return box


def mesh_of(body):
    try:
        mesh = body.tessellate(
            chord_height_tolerance=0.1, surface_angle_tolerance_deg=15.0
        )
    except sm.TessellationError:
        # One bounded presentation repair. CAD parameters and locks do not change.
        mesh = body.tessellate(
            chord_height_tolerance=0.05, surface_angle_tolerance_deg=10.0
        )
    arrays = mesh.to_mesh_arrays()
    # VTK-style count-prefixed polygons, not a plain triangle index array.
    stream = arrays["faces"]
    cursor = 0
    faces = []
    while cursor < len(stream):
        count = int(stream[cursor])
        cursor += 1
        polygon = stream[cursor : cursor + count]
        cursor += count
        if count < 3 or len(polygon) != count:
            raise ValueError("Invalid tessellation polygon stream.")
        for n in range(1, count - 1):
            faces.append((polygon[0], polygon[n], polygon[n + 1]))
    return Mesh(
        vertices=tuple(tuple(p) for p in arrays["points"]),
        triangles=tuple(tuple(int(n) for n in t) for t in faces),
    )


def execute(plan, analysis, path):
    plan = Plan.model_validate(plan.model_dump())
    if plan.source_hash != analysis.source_hash:
        raise ValueError("Plan/source hash mismatch.")
    i = get_interface(analysis, plan.interface_id)
    lookup = dict(zip(i.hole_ids, i.centers))
    # Resolve every measured reference before touching native state.
    for op in plan.operations:
        if op.kind == "mount" and (
            not op.diameter or not op.hole_ids or not set(op.hole_ids) <= set(lookup)
        ):
            raise ValueError("Invalid measured mounting references or diameter.")
    with KERNEL_LOCK:
        bodies = {}
        cuts = []
        support_checks = []
        for op in plan.operations:
            if op.kind == "place":
                continue
            if op.kind == "stock":
                bodies[op.body] = primitive(op)
            elif op.kind == "support":
                support = primitive(op)
                distance = bodies[op.target].distance_to(support)
                if distance > MM_TOL:
                    raise ValueError("Support is disconnected from its parent.")
                bodies[op.body] = support
                support_checks.append(distance)
            elif op.kind == "mount":
                for n in op.instance_ids:
                    for hid in op.hole_ids:
                        c = np.array(lookup[hid]) + plan.placements[n]
                        tool = sm.primitives.create_cylinder(
                            (float(c[0]), float(c[1]), op.origin[2]),
                            op.diameter / 2,
                            op.size[2],
                        )
                        old = bodies[op.target].volume()
                        bodies[op.target] = sm.booleans.boolean_difference(
                            bodies[op.target], tool
                        )
                        if old - bodies[op.target].volume() <= MM_TOL:
                            raise ValueError(f"Mounting cut {hid} missed stock.")
                        cuts.append(
                            dict(
                                body=op.target,
                                instance=n,
                                feature=hid,
                                center=c.tolist(),
                                diameter=op.diameter,
                            )
                        )
            elif op.kind == "relief":
                for target in op.targets or (op.target,):
                    bodies[target] = sm.booleans.boolean_difference(
                        bodies[target], primitive(op)
                    )
            elif op.kind == "combine":
                fn = (
                    sm.booleans.boolean_union
                    if op.mode == "union"
                    else sm.booleans.boolean_difference
                )
                bodies[op.target] = fn(bodies[op.target], bodies.pop(op.other))
            elif op.kind == "fillet":
                from .fillets import apply_fillet

                bodies[op.target] = apply_fillet(bodies[op.target], op)
            elif op.kind == "finish":
                bodies[op.target] = sm.booleans.boolean_intersection(
                    bodies[op.target], primitive(op)
                )
        if not bodies:
            raise ValueError("Plan produced no bodies.")
        for name, b in bodies.items():
            if (
                not b.is_manifold_solid()
                or b.volume() <= 0
                or b.material_census()["solid_count"] != 1
            ):
                raise ValueError(
                    f"{name} contains invalid or detached material. Revise stock or access cuts."
                )
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        export_verified(bodies.values(), path, str(plan.parameters.get("up_axis", "Z")))
        meshes = {name: mesh_of(b) for name, b in bodies.items()}
        return bodies, meshes, cuts
