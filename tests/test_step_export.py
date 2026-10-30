import io
import json
import zipfile

import cadquery as cq
import pytest

from fixture.project import Project
from fixture.step_export import prepare_step, prepared_step
from tests.test_geometry import ready


@pytest.mark.parametrize(
    "composition,quantity",
    [("plate", 1), ("rails", 2), ("l_bracket", 1), ("bridge", 2)],
)
def test_step_roundtrip_all_fixture_families(composition, quantity):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    a, r = ready(
        composition=composition,
        quantity=quantity,
        clearance_diameter=None,
        nominal_fastener="M3",
        surroundings="bolt",
    )
    p = Project(a, r)
    rev = p.generate()
    path = prepare_step(rev)
    assert path.read_text().startswith("ISO-10303-21;")
    assert "FACETED_BREP" not in path.read_text()
    shapes = cq.importers.importStep(str(path)).val().Solids()
    assert len(shapes) == rev.metrics["body_count"]
    assert all(s.isValid() for s in shapes)
    radii = [
        BRepAdaptor_Surface(f.wrapped).Cylinder().Radius()
        for s in shapes
        for f in s.Faces()
        if BRepAdaptor_Surface(f.wrapped).GetType() == GeomAbs_Cylinder
    ]
    assert len(radii) >= 4 * quantity
    assert all(radius == pytest.approx(1.7, abs=1e-6) for radius in radii)
    report = json.loads(path.with_name("step-export.json").read_text())
    assert report["result"] == "passed" and report["units"] == "mm"
    assert len(report["bodies"]) == len(shapes)
    assert all(
        abs(b["volume_mm3"] - b["native_volume_mm3"]) < 0.01 for b in report["bodies"]
    )
    stamp = path.stat().st_mtime_ns
    assert prepare_step(rev) == path and path.stat().st_mtime_ns == stamp
    with zipfile.ZipFile(io.BytesIO(p.export())) as archive:
        assert archive.read("fixture.step") == path.read_bytes()
        assert "step-export.json" in archive.namelist()
        assert [n for n in archive.namelist() if n.endswith(".step")] == [
            "fixture.step"
        ]


def test_rear_clearance_prism_and_cylinder_transfer(tmp_path):
    from tests.test_clearance import protruding_source

    a, r, _ = protruding_source(tmp_path)
    rev = Project(a, r).generate()
    path = prepare_step(rev)
    assert prepared_step(rev) == path
    assert cq.importers.importStep(str(path)).val().isValid()


def test_cache_corruption_and_failed_transfer_preserve_previous_step(monkeypatch):
    import fixture.step_export as exporter

    a, r = ready()
    p = Project(a, r)
    rev = p.generate()
    path = prepare_step(rev)
    saved = path.read_bytes()
    path.write_text("corrupt")
    assert prepared_step(rev) is None
    assert "fixture.step" not in zipfile.ZipFile(io.BytesIO(p.export())).namelist()
    prepare_step(rev)
    assert prepared_step(rev) == path
    restored = path.read_bytes()
    native = path.with_suffix(".usda")
    native.write_text(native.read_text() + "\n# invalidate hash\n")

    def fail(_):
        raise ValueError("Injected unsupported geometry")

    monkeypatch.setattr(exporter, "_body", fail)
    with pytest.raises(ValueError, match="unsupported"):
        prepare_step(rev)
    assert path.read_bytes() == restored
    assert prepared_step(rev) is None and p.current.id == rev.id
    assert saved.startswith(b"ISO-10303-21;")
