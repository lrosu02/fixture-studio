import numpy as np
import usd_brep as sm

from fixture.executor import mesh_of
from fixture.render_mesh import display_indices


def test_planar_wall_normals_do_not_blend_with_bores_or_corners():
    wall = sm.primitives.create_box((-20.0, -15.0, -6.0), 40.0, 30.0, 6.0)
    wall = sm.booleans.boolean_difference(
        wall, sm.primitives.create_cylinder((0.0, 0.0, -7.0), 3.0, 8.0)
    )
    mesh = mesh_of(wall)
    indices, triangles = display_indices(mesh)
    points = np.asarray(mesh.vertices)
    before = points[np.asarray(mesh.triangles)]
    after = points[indices][triangles]
    assert np.array_equal(before, after)  # Shading only; zero coordinate changes.
    normals = np.cross(after[:, 1] - after[:, 0], after[:, 2] - after[:, 0])
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    top = np.all(np.abs(after[:, :, 2]) < 1e-8, axis=1)
    assert top.any()
    top_vertices = set(triangles[top].flat)
    # Every incident triangle at a top-face vertex is in that same plane.
    assert all(
        abs(normals[n, 2]) > 1 - 1e-8
        for n, tri in enumerate(triangles)
        if any(v in top_vertices for v in tri)
    )
    assert len(indices) < 3 * len(triangles)  # Curves and coplanar faces remain shared.
    assert display_indices(mesh)[0] is indices  # Re-renders reuse the split topology.


def test_curved_tessellation_keeps_smoothing_between_adjacent_segments():
    mesh = mesh_of(sm.primitives.create_cylinder((0.0, 0.0, 0.0), 10.0, 8.0))
    indices, triangles = display_indices(mesh)
    points = np.asarray(mesh.vertices)[indices]
    facets = points[triangles]
    side = np.ptp(facets[:, :, 2], axis=1) > 1
    counts = np.bincount(triangles[side].flatten(), minlength=len(points))
    assert counts.max() > 2
    for t in triangles[~side]:
        assert all(counts[v] == 0 for v in t)  # Cap shading remains separate.
