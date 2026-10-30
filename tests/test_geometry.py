from pathlib import Path
import numpy as np
import pytest
from fixture.contracts import Requirements
from fixture.intake import analyze_file, recommended_interface
from fixture.planning import compile_plan
from fixture.executor import execute, mesh_of

ROOT = Path(__file__).resolve().parents[1]


def ready(name="synthetic_motor.step", **updates):
    a = analyze_file(ROOT / "samples" / name)
    r = Requirements(
        purpose="Inspection",
        quantity=1,
        interface_id=recommended_interface(a),
        mounting_confirmed=True,
        clearance_diameter=3.5,
        surroundings="clamp",
        fabrication="Machined stock",
        motion_loads="unknown",
        access="rear tools",
        assumptions_accepted=True,
    )
    return a, r.model_copy(update=updates)


@pytest.mark.parametrize("composition", ["plate", "rails"])
def test_compositions(composition):
    a, r = ready(composition=composition)
    p = compile_plan(a, r)
    bodies, meshes, cuts = execute(p, a, ROOT / "artifacts" / f"{composition}.usda")
    assert len(bodies) == (1 if composition == "plate" else 2)
    assert len(cuts) == 4
    assert all(b.is_manifold_solid() for b in bodies.values())
    assert all(len(m.triangles) > 0 for m in meshes.values())
    if composition == "plate":
        expected = 64 * 52 * 6 - 4 * np.pi * (3.5 / 2) ** 2 * 6
        assert sum(b.volume() for b in bodies.values()) == pytest.approx(
            expected, abs=0.02
        )


@pytest.mark.parametrize(
    "quantity,layout,columns", [(2, "row", 2), (6, "grid", 3), (3, "grid", 2)]
)
def test_quantity_and_layout(quantity, layout, columns):
    a, r = ready(
        quantity=quantity,
        layout=layout,
        columns=columns,
        surroundings="bolt",
        bench_hole_diameter=4,
    )
    p = compile_plan(a, r)
    bodies, meshes, cuts = execute(
        p, a, ROOT / "artifacts" / f"quantity-{quantity}.usda"
    )
    assert len(p.placements) == quantity and len(cuts) == quantity * 4
    interface = next(i for i in a.interfaces if i.id == r.interface_id)
    for cut in cuts:
        expected = (
            np.array(interface.centers[interface.hole_ids.index(cut["feature"])])
            + p.placements[cut["instance"]]
        )
        assert cut["center"] == pytest.approx(expected)
    assert (
        sum(
            op.purpose == "Surrounding attachment bolt clearance" for op in p.operations
        )
        == 2
    )


def test_unrelated_fixture():
    a, r = ready("sensor_bracket.step", clearance_diameter=4.5)
    p = compile_plan(a, r)
    bodies, meshes, cuts = execute(p, a, ROOT / "artifacts" / "sensor.usda")
    assert len(cuts) == 3


def test_native_preview_mesh_matches_box_volume():
    import usd_brep as sm

    mesh = mesh_of(sm.primitives.create_box((0.0, 0.0, 0.0), 10.0, 10.0, 2.0))
    assert len(mesh.triangles) == 12
    points = np.array(mesh.vertices)
    volume = abs(
        sum(
            np.dot(points[a], np.cross(points[b], points[c])) / 6
            for a, b, c in mesh.triangles
        )
    )
    assert volume == pytest.approx(200)
