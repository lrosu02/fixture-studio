"""Prove perpendicular holes and triangular support sweeps in installed SMLib."""

import json
from pathlib import Path
import usd_brep as sm


def main():
    wall = sm.primitives.create_box((0.0, 0.0, -6.0), 40.0, 35.0, 6.0)
    foot = sm.primitives.create_box((0.0, -6.0, -35.0), 40.0, 9.0, 35.0)
    solid = sm.booleans.boolean_union(wall, foot)
    points = [(0.0, 0.0, -30.0), (0.0, 25.0, -3.0), (0.0, 0.0, -3.0)]
    curves = [
        sm.curves.create_line_segment(points[n], points[(n + 1) % 3]) for n in range(3)
    ]
    rib = sm.sweeps.linear_sweep(curves, (1.0, 0.0, 0.0), 5.0, cap_ends=True)
    assert abs(rib.volume(1e-7) - 25 * 27 * 5 / 2) < 0.01
    solid = sm.booleans.boolean_union(solid, rib)
    cylinder = sm.primitives.create_cylinder((20.0, -7.0, -22.0), 2.0, 11.0)
    cylinder = sm.transforms.rotate(
        cylinder, (20.0, -7.0, -22.0), (1.0, 0.0, 0.0), -90.0
    )
    before = solid.volume(1e-7)
    solid = sm.booleans.boolean_difference(solid, cylinder)
    assert abs(before - solid.volume(1e-7) - 3.141592653589793 * 4 * 9) < 0.01
    assert solid.is_manifold_solid() and solid.material_census()["solid_count"] == 1
    out = Path(__file__).resolve().parents[1] / "artifacts" / "feasibility"
    out.mkdir(parents=True, exist_ok=True)
    sm.usd.export_brep(solid, str(out / "perpendicular.usda"))
    (reopened,) = sm.usd.import_breps(str(out / "perpendicular.usda"))
    assert abs(reopened.volume(1e-7) - solid.volume(1e-7)) < 0.01
    report = dict(
        volume_mm3=solid.volume(1e-7),
        bounds=solid.bounding_box(),
        triangular_sweep=True,
        perpendicular_bore=True,
        round_trip=True,
    )
    (out / "structures.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
