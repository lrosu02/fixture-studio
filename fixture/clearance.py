"""Measured rear envelopes. No feature identity, screw pattern or part template.

Connected clipped mesh patches get separate enclosing cylinders or convex prisms.
The mesh is evidence for conservative envelopes, not an exact source BRep bridge.
"""

from collections import OrderedDict
from threading import RLock
import numpy as np
from .contracts import Operation, MM_TOL
from .intake import local_points

MAX_REAR_REGIONS = 32
_CACHE = OrderedDict()
_LOCK = RLock()


def convex_hull(points):
    """Monotone chain, preserving the measured coordinates (no fitted contour)."""
    points = sorted(set(map(tuple, points)))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for chain, ordered in ((lower, points), (upper, reversed(points))):
        for p in ordered:
            while len(chain) >= 2 and cross(chain[-2], chain[-1], p) <= 1e-9:
                chain.pop()
            chain.append(p)
    return np.array(lower[:-1] + upper[:-1], dtype=float)


def _clipped_components(points, triangles):
    facets = points[np.asarray(triangles)]
    facets = facets[facets[:, :, 2].min(axis=1) < -MM_TOL]
    if not len(facets):
        return ()
    # OCCT duplicates shared vertices at face seams. Welding affects adjacency
    # only; all envelope coordinates below remain the original measured values.
    roots = list(range(len(facets)))

    def root(n):
        while roots[n] != n:
            roots[n] = roots[roots[n]]
            n = roots[n]
        return n

    owner = {}
    for n, facet in enumerate(facets):
        for vertex in facet:
            # Vertices on the source side must not join otherwise separate rear patches.
            if vertex[2] > MM_TOL:
                continue
            key = tuple(np.rint(vertex / 1e-6).astype(np.int64))
            other = owner.setdefault(key, n)
            roots[root(n)] = root(other)
    groups = {}
    for n, facet in enumerate(facets):
        clipped = [p for p in facet if p[2] <= 0]
        for k in range(3):
            u, v = facet[k], facet[(k + 1) % 3]
            if (u[2] < 0) != (v[2] < 0):
                clipped.append(u + (v - u) * (-u[2] / (v[2] - u[2])))
        if clipped:
            groups.setdefault(root(n), []).extend(clipped)
    result = [np.unique(np.array(group), axis=0) for group in groups.values()]
    # Mesh face traversal cannot affect operation order or exported reproduction.
    result.sort(key=lambda p: tuple(p.min(axis=0)) + tuple(p.max(axis=0)))
    if len(result) > MAX_REAR_REGIONS:
        raise ValueError(
            f"Rear geometry needs {len(result)} separate clearances; the bounded limit is {MAX_REAR_REGIONS}. No protrusions were dropped."
        )
    return tuple(result)


def offset_profile(points, padding):
    hull = convex_hull(points)
    if len(hull) < 3:
        # A thin projected edge still needs a finite conservative cut.
        lo, hi = points.min(axis=0) - padding, points.max(axis=0) + padding
        return np.array(
            [(lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1])]
        )
    if len(hull) <= 48:
        edges = np.roll(hull, -1, axis=0) - hull
        normals = np.column_stack((edges[:, 1], -edges[:, 0]))
        normals /= np.linalg.norm(normals, axis=1)[:, None]
        distances = (normals * hull).sum(axis=1) + padding
    else:
        # Bounded supporting half-planes enclose the entire hull; never simplify
        # by dropping measured vertices and shrinking the forbidden region.
        theta = np.linspace(0, 2 * np.pi, 48, endpoint=False)
        normals = np.column_stack((np.cos(theta), np.sin(theta)))
        distances = (hull @ normals.T).max(axis=0) + padding
    expanded = [
        np.linalg.solve(normals[[n - 1, n]], distances[[n - 1, n]])
        for n in range(len(normals))
    ]
    return convex_hull(expanded)


def stable_profile(points, padding):
    """Intersect supporting half-planes, avoiding nearly parallel mesh edges.

    Every half-plane contains the measured XY points plus requested padding.
    Clipping handles redundant constraints without weakening the CAD contract.
    """
    lo, hi = points.min(axis=0) - padding, points.max(axis=0) + padding
    polygon = [lo, np.array((hi[0], lo[1])), hi, np.array((lo[0], hi[1]))]
    for angle in np.linspace(0, 2 * np.pi, 32, endpoint=False):
        normal = np.array((np.cos(angle), np.sin(angle)))
        distance = float((points @ normal).max() + padding)
        clipped = []
        for n, end in enumerate(polygon):
            start = polygon[n - 1]
            ds, de = float(start @ normal - distance), float(end @ normal - distance)
            if (ds <= 0) != (de <= 0):
                clipped.append(start + (end - start) * (ds / (ds - de)))
            if de <= 0:
                clipped.append(end)
        polygon = clipped
    return convex_hull(polygon)


def _region(points, padding, index):
    xy = points[:, :2]
    polygon = offset_profile(xy, padding)
    lo, hi = polygon.min(axis=0), polygon.max(axis=0)
    z0, z1 = float(points[:, 2].min() - padding), float(points[:, 2].max() + padding)
    center = (xy.min(axis=0) + xy.max(axis=0)) / 2
    radius = float(np.linalg.norm(xy - center, axis=1).max() + padding)
    area = (
        abs(
            np.dot(polygon[:, 0], np.roll(polygon[:, 1], -1))
            - np.dot(polygon[:, 1], np.roll(polygon[:, 0], -1))
        )
        / 2
    )
    common = dict(
        id=f"rear-profile-{index}",
        kind="relief",
        target="mounting-platform",
        purpose="Measured rear protrusion clearance",
        provenance={"profile": "measured", "padding": "derived"},
    )
    if np.pi * radius**2 <= area * 1.08:
        return Operation(
            **common,
            shape="cylinder",
            origin=(*center, z0),
            size=(2 * radius, 2 * radius, z1 - z0),
        )
    try:
        return Operation(
            **common,
            shape="prism",
            origin=(*lo, z0),
            size=(*tuple(hi - lo), z1 - z0),
            profile=tuple(map(tuple, polygon - lo)),
        )
    except ValueError as error:
        if "Prism profile" not in str(error):
            raise
        polygon = stable_profile(xy, padding)
        lo, hi = polygon.min(axis=0), polygon.max(axis=0)
        return Operation(
            **{
                **common,
                "provenance": {**common["provenance"], "stable_envelope": "derived"},
            },
            shape="prism",
            origin=(*lo, z0),
            size=(*tuple(hi - lo), z1 - z0),
            profile=tuple(map(tuple, polygon - lo)),
        )


def rear_regions(analysis, interface, padding):
    """Bounded cache keyed by immutable mesh identity; retains that mesh to avoid ID reuse."""
    key = (
        id(analysis.mesh),
        interface.origin,
        interface.x,
        interface.y,
        interface.z,
        float(padding),
    )
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key][1]
    points = local_points(analysis.mesh.vertices, interface)
    groups = _clipped_components(points, analysis.mesh.triangles)
    regions = tuple(_region(p, padding, n) for n, p in enumerate(groups))
    with _LOCK:
        _CACHE[key] = (analysis.mesh, regions)
        while len(_CACHE) > 8:
            _CACHE.popitem(last=False)
    return regions


def footprint_distance(op, point):
    """Distance to the filled XY region, including zero for interior points."""
    p = np.asarray(point)[:2] - op.origin[:2]
    if op.shape == "cylinder":
        return max(0.0, float(np.linalg.norm(p) - op.size[0] / 2))
    if op.shape == "box":
        return float(np.linalg.norm(p - np.clip(p, (0, 0), op.size[:2])))
    polygon = np.array(op.profile)
    nxt = np.roll(polygon, -1, axis=0)
    edges = nxt - polygon
    deltas = p - polygon
    cross = edges[:, 0] * deltas[:, 1] - edges[:, 1] * deltas[:, 0]
    if np.all(cross >= -1e-9):
        return 0.0
    t = np.clip((edges * deltas).sum(axis=1) / (edges * edges).sum(axis=1), 0, 1)
    return float(np.linalg.norm(p - (polygon + t[:, None] * edges), axis=1).min())


def placed_regions(analysis, interface, padding, placements):
    return tuple(
        op.model_copy(
            update={
                "id": f"rear-relief-{n}-{k}",
                "origin": tuple(np.array(op.origin) + p),
            }
        )
        for n, p in enumerate(placements)
        for k, op in enumerate(rear_regions(analysis, interface, padding))
    )


def fixture_regions(analysis, interface, requirements, placements, stock_ops):
    """Extend only selected measured profiles through the complete fixture in Z.

    Referencing a measured profile preserves its XY outline. Depth comes from
    fixture stock/support extents, so thicker revisions cannot leave a blind cap.
    """
    profiles = rear_regions(analysis, interface, requirements.rear_clearance)
    selected = requirements.rear_passages
    if len(set(selected)) != len(selected) or not set(selected) <= {
        p.id for p in profiles
    }:
        raise ValueError(
            "Through passage references an unknown or duplicate measured rear profile. Reselect it for the current mounting face."
        )
    regions = placed_regions(
        analysis, interface, requirements.rear_clearance, placements
    )
    from .manufacturing import is_sheet_metal

    if is_sheet_metal(requirements.fabrication):
        # Flat cut sheets cannot contain blind relief pockets.
        selected = tuple(p.id for p in profiles)
    if not selected:
        return regions
    stocks = [op for op in stock_ops if op.kind in ("stock", "support")]
    z0 = min(op.origin[2] for op in stocks) - 1
    z1 = max(op.origin[2] + op.size[2] for op in stocks) + 1
    result = []
    for n, region in enumerate(regions):
        if profiles[n % len(profiles)].id in selected:
            lo = min(z0, region.origin[2])
            hi = max(z1, region.origin[2] + region.size[2])
            region = region.model_copy(
                update={
                    "origin": (*region.origin[:2], lo),
                    "size": (*region.size[:2], hi - lo),
                    "purpose": "Through passage from selected measured rear profile",
                    "provenance": {
                        **region.provenance,
                        "through": requirements.provenance.get("rear_passages", "user"),
                        "depth": "derived",
                    },
                }
            )
        result.append(region)
    return tuple(result)


def passage_options(analysis, requirements):
    """Measured choices for conversation and UI; no inferred cable/shaft identity."""
    from .intake import selected_interface

    interface = selected_interface(analysis, requirements)
    return [
        dict(
            id=op.id,
            shape=op.shape,
            minimum_z=op.origin[2],
            center_xy=op.origin[:2]
            if op.shape == "cylinder"
            else tuple(op.origin[k] + op.size[k] / 2 for k in (0, 1)),
            width_mm=op.size[0],
            height_mm=op.size[1],
            blind_in_wall=-op.origin[2] < requirements.thickness,
            through_selected=op.id in requirements.rear_passages,
        )
        for op in rear_regions(analysis, interface, requirements.rear_clearance)
    ]
