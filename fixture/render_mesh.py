"""Presentation-only crease splitting for correct smooth CAD preview shading."""

from collections import OrderedDict
from threading import RLock
import numpy as np

_CACHE = OrderedDict()
_LOCK = RLock()


def display_indices(mesh):
    """Keep curved tessellation smooth without averaging normals across corners.

    Plotly computes vertex normals from the indexed triangles. SMLib shares
    vertices across wall/bore/rib boundaries, so using those indices unchanged
    makes large flat faces appear dented. Split only the shading topology at
    creases over 30 degrees. Every triangle coordinate is unchanged.
    """
    key = id(mesh)
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key][1:]
    points, triangles = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    facets = points[triangles]
    normals = np.cross(facets[:, 1] - facets[:, 0], facets[:, 2] - facets[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    normals /= np.maximum(lengths[:, None], 1e-20)
    roots = list(range(3 * len(triangles)))

    def root(n):
        while roots[n] != n:
            roots[n] = roots[roots[n]]
            n = roots[n]
        return n

    edges = {}
    for face, tri in enumerate(triangles):
        for k in range(3):
            a, b = int(tri[k]), int(tri[(k + 1) % 3])
            edges.setdefault(tuple(sorted((a, b))), []).append(
                (face, {a: face * 3 + k, b: face * 3 + (k + 1) % 3})
            )
    limit = np.cos(np.deg2rad(30))
    for (a, b), uses in edges.items():
        if len(uses) != 2:
            continue
        (f, left), (g, right) = uses
        if (
            lengths[f] > 1e-20
            and lengths[g] > 1e-20
            and normals[f] @ normals[g] >= limit
        ):
            for v in (a, b):
                roots[root(left[v])] = root(right[v])
    groups, indices, remapped = {}, [], []
    for corner, vertex in enumerate(triangles.flat):
        group = root(corner)
        if group not in groups:
            groups[group] = len(indices)
            indices.append(int(vertex))
        remapped.append(groups[group])
    indices = np.array(indices, dtype=int)
    remapped = np.array(remapped, dtype=int).reshape((-1, 3))
    with _LOCK:
        _CACHE[key] = (mesh, indices, remapped)
        while len(_CACHE) > 8:
            _CACHE.popitem(last=False)
    return indices, remapped
