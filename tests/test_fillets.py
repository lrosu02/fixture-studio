import io
import zipfile

import cadquery as cq
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder

from fixture.executor import execute
from fixture.planning import compile_plan, patch_requirements
from fixture.project import Project
from fixture.step_export import prepare_step
from fixture.validation import validate
from tests.test_geometry import ready


@pytest.mark.parametrize("method", ["3D printing", "Machined stock"])
def test_rounded_ribs_preserve_five_base_holes_and_through_access(method, tmp_path):
    from fixture.contracts import Envelope

    a, r = ready(
        composition="l_bracket",
        fabrication=method,
        manufacturing_features=True,
        surroundings="bolt",
        bench_hole_diameter=3.4,
        bench_hole_count=5,
        mount_height=70,
        base_depth=45,
        envelopes=(
            Envelope(
                id="wire",
                minimum=(-4, -40, -9),
                maximum=(4, -32, 1),
                purpose="Through cable passage",
            ),
        ),
    )
    p = Project(a, r)
    revision = p.generate()
    fillets = [op for op in revision.plan.operations if op.kind == "fillet"]
    assert len(fillets) == 1 and fillets[0].fillet_radius == 1.5
    assert revision.plan.parameters["base_hole_count"] == 5
    assert all(
        c.result == "passed"
        for c in revision.checks
        if c.name.startswith("Rib root fillet")
    )
    step = cq.importers.importStep(str(prepare_step(revision))).val()
    assert step.isValid() and len(step.Solids()) == 1
    curved = [
        BRepAdaptor_Surface(f.wrapped).Cylinder().Radius()
        for f in step.Faces()
        if BRepAdaptor_Surface(f.wrapped).GetType() == GeomAbs_Cylinder
    ]
    assert sum(abs(rad - 1.5) < 1e-6 for rad in curved) == 2
    # Test the exported solid itself, including full wall thickness.
    passage = cq.Solid.makeBox(7.8, 7.8, 8, cq.Vector(-3.9, -39.9, -7))
    assert step.intersect(passage).Volume() < 0.01
    if method == "3D printing":
        archive = tmp_path / "filleted.zip"
        archive.write_bytes(p.export())
        from scripts.reproduce import reproduce

        reproduce(archive, tmp_path / "reproduced")
        with zipfile.ZipFile(io.BytesIO(p.export())) as bundle:
            assert b'"rib_fillet_radius_mm": 1.5' in bundle.read("plan.json")


def test_fillet_revision_disable_bounds_locks_and_legacy_reproduction(tmp_path):
    a, r = ready(composition="l_bracket", mount_height=70, base_depth=40)
    p = Project(a, r)
    first = p.generate()
    sharp = p.generate(patch_requirements(r, {"auto_rib_fillets": False}))
    assert sharp.metrics["volume_mm3"] < first.metrics["volume_mm3"]
    p.restore(first.id)
    with pytest.raises(ValueError, match="at most"):
        p.generate(patch_requirements(r, {"rib_fillet_radius": 5}))
    assert p.current.id == first.id
    with pytest.raises(ValueError, match="locked"):
        patch_requirements(
            r.model_copy(update={"locks": ("auto_rib_fillets",)}),
            {"auto_rib_fillets": False},
        )
    old = compile_plan(a, r, compiler_version=9)
    assert not any(op.kind == "fillet" for op in old.operations)
    b, _, c = execute(old, a, tmp_path / "old.usda")
    assert all(check.result != "failed" for check in validate(a, r, old, b, c))
    # Removing a fillet operation must fail independent native material checks.
    expected = compile_plan(a, r)
    checks = validate(a, r, expected, b, c)
    assert any(
        check.name.startswith("Rib root fillet") and check.result == "failed"
        for check in checks
    )


def test_fillet_settings_are_lock_aware_and_persist_without_build():
    from streamlit.testing.v1 import AppTest
    from tests.test_geometry import ROOT

    a, r = ready(composition="l_bracket")
    p = Project(a, r)
    ui = AppTest.from_string(
        "from fixture.controls import fillet_controls\nimport streamlit as st\nfillet_controls(st.session_state.project)"
    )
    ui.session_state.project = p
    ui.run()
    ui.number_input[0].set_value(1.0).run()
    ui.button[0].click().run()
    assert not ui.exception and p.requirements.rib_fillet_radius == 1
    assert not p.revisions
    assert (
        Project.load(ROOT / "artifacts" / p.id / "project.json").requirements
        == p.requirements
    )
