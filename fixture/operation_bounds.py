"""Analytic bounds for the small operation vocabulary, without native calls."""

import numpy as np


def bounds(op):
    origin = np.array(op.origin)
    size = np.array(op.size)
    if op.shape not in ("cylinder", "cone", "prism"):
        return origin, origin + size
    k = "xyz".index(op.axis)
    if op.shape in ("cylinder", "cone"):
        radius = (max(size[:2]) if op.shape == "cone" else size[0]) / 2
        lo = origin - np.array([radius] * 3)
        hi = origin + radius
        lo[k] = origin[k]
        hi[k] = origin[k] + size[2]
        return lo, hi
    points = np.array([(u, v, z) for u, v in op.profile for z in (0, size[2])])
    if op.axis == "y":
        points = points[:, [0, 2, 1]] * np.array([1, 1, -1])
    if op.axis == "x":
        points = points[:, [2, 1, 0]] * np.array([1, 1, -1])
    return points.min(axis=0) + origin, points.max(axis=0) + origin
