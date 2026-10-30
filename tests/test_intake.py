from pathlib import Path
import numpy as np
import pytest
from fixture.intake import analyze_file, local_points, recommended_interface

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def test_reference_pattern():
    a = analyze_file(SAMPLES / "synthetic_motor.step")
    i = next(i for i in a.interfaces if i.id == recommended_interface(a))
    assert len(i.centers) == 4
    assert i.diameters == pytest.approx([4] * 4)
    assert np.ptp(np.array(i.centers), axis=0)[:2] == pytest.approx([34, 22])
    assert i.contact_ok
    assert a.original_units


def test_unrelated_and_ambiguous():
    a = analyze_file(SAMPLES / "sensor_bracket.step")
    assert any(
        len(i.centers) == 3 and np.allclose(i.diameters, 5) for i in a.interfaces
    )
    assert recommended_interface(analyze_file(SAMPLES / "ambiguous.step")) is None
    assert not analyze_file(SAMPLES / "unsupported_sphere.step").interfaces


def test_transform_and_bodies():
    a = analyze_file(SAMPLES / "synthetic_motor.step")
    b = analyze_file(SAMPLES / "transformed_motor.step")
    ia = next(i for i in a.interfaces if i.id == recommended_interface(a))
    ib = next(i for i in b.interfaces if i.id == recommended_interface(b))
    assert np.sort(
        np.linalg.norm(np.array(ia.centers)[:, None] - ia.centers, axis=2).ravel()
    ) == pytest.approx(
        np.sort(
            np.linalg.norm(np.array(ib.centers)[:, None] - ib.centers, axis=2).ravel()
        ),
        abs=1e-5,
    )
    assert np.ptp(local_points(a.mesh.vertices, ia), axis=0) == pytest.approx(
        np.ptp(local_points(b.mesh.vertices, ib), axis=0), abs=0.03
    )
    group = analyze_file(SAMPLES / "multi_body.step")
    assert group.body_count == 2
    chosen = analyze_file(SAMPLES / "multi_body.step", (0,))
    assert chosen.selected_bodies == (0,)


def test_chamfer_bore_and_reject_slot(tmp_path):
    import cadquery as cq

    part = (
        cq.Workplane("XY")
        .box(40, 30, 8)
        .faces(">Z")
        .workplane()
        .pushPoints([(-12, -8), (12, -8), (12, 8), (-12, 8)])
        .hole(4)
    )
    chamfered = part.faces(">Z").edges("%CIRCLE").chamfer(0.5)
    path = tmp_path / "chamfer.step"
    cq.exporters.export(chamfered, str(path))
    analysis = analyze_file(path)
    drilled = [i for i in analysis.interfaces if i.hole_ids]
    assert len(drilled) == 2
    assert all(i.diameters == pytest.approx([4] * 4) for i in drilled)
    slot = (
        cq.Workplane("XY")
        .box(30, 20, 6)
        .cut(cq.Workplane("XY").workplane(offset=-5).slot2D(12, 4).extrude(10))
    )
    path = tmp_path / "slot.step"
    cq.exporters.export(slot, str(path))
    assert analyze_file(path).interfaces
    assert all(not i.hole_ids for i in analyze_file(path).interfaces)


def test_declared_inch_normalization(tmp_path):
    import cadquery as cq

    part = cq.Workplane("XY").box(50.8, 25.4, 6.35)
    path = tmp_path / "inches.step"
    part.val().exportStep(str(path), unit="MM", outputUnit="INCH")
    a = analyze_file(path)
    assert np.array(a.bounds[1]) - a.bounds[0] == pytest.approx([50.8, 25.4, 6.35])
    assert any("inch" in u.lower() for u in a.original_units)
