"""Stage 1: exercise both native kernels in the same Python process."""

from pathlib import Path
import json
import math
import importlib.metadata as md
import cadquery as cq
import usd_brep as sm

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "artifacts" / "feasibility"
    out.mkdir(parents=True, exist_ok=True)
    sample = (
        cq.Workplane("XY")
        .box(40, 30, 8)
        .faces(">Z")
        .workplane()
        .pushPoints([(-12, -8), (12, -8), (12, 8), (-12, 8)])
        .hole(4)
    )
    cq.exporters.export(sample, str(out / "reference.step"))
    imported = cq.importers.importStep(str(out / "reference.step")).val()
    vertices, triangles = imported.tessellate(0.1)
    assert imported.isValid() and len(triangles) > 20
    box = sm.primitives.create_box((0.0, 0.0, 0.0), 40.0, 30.0, 8.0)
    tool = sm.primitives.create_cylinder((20.0, 15.0, -1.0), 2.0, 10.0)
    solid = sm.booleans.boolean_difference(box, tool)
    expected = 40 * 30 * 8 - math.pi * 2**2 * 8
    assert solid.is_manifold_solid()
    assert abs(solid.volume() - expected) < 0.01
    sm.usd.export_brep(solid, str(out / "solid.usda"))
    (reopened,) = sm.usd.import_breps(str(out / "solid.usda"))
    assert reopened.is_manifold_solid()
    assert abs(reopened.volume() - solid.volume()) < 0.01
    mesh = reopened.tessellate(surface_angle_tolerance_deg=15.0)
    report = dict(
        versions={
            p: md.version(p)
            for p in [
                "cadquery",
                "cadquery-ocp",
                "usd-brep",
                "streamlit",
                "plotly",
                "pydantic",
                "openai",
                "pytest",
            ]
        },
        source_triangles=len(triangles),
        fixture_volume_mm3=solid.volume(),
        reopened_volume_mm3=reopened.volume(),
        bounds=solid.bounding_box(),
        mesh_points=len(mesh.get_points()),
        same_process=True,
    )
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
