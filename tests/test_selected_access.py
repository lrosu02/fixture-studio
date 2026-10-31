from types import SimpleNamespace
from pathlib import Path
import pytest
import cadquery as cq
from fixture.contracts import AccessSelection
from fixture.access import probes
from fixture.executor import execute, primitive
from fixture.planning import compile_plan, patch_requirements
from fixture.project import Project
from fixture.validation import validate
from fixture.step_export import prepare_step
from tests.test_passages import shallow_source


def test_full_depth_bounds_include_horizontal_cylindrical_stock():
    from fixture.operation_bounds import bounds
    from fixture.contracts import Operation

    op = Operation(
        id="collar",
        kind="stock",
        body="collar",
        shape="cylinder",
        axis="y",
        origin=(0, -5, 10),
        size=(30, 30, 10),
        provenance={"size": "derived"},
    )
    low, high = bounds(op)
    assert tuple(low) == (-15, -5, -5) and tuple(high) == (15, 5, 25)


def test_click_selected_recess_is_through_after_thickness_revision(tmp_path):
    a, r, profile = shallow_source(tmp_path)
    r = patch_requirements(
        r,
        {
            "through_access_required": True,
            "access_selections": (
                AccessSelection(feature_id="rear:" + profile, padding=0.3),
            ),
        },
    )
    p = Project(a, r)
    first = p.generate()
    second = p.generate(patch_requirements(r, {"thickness": 8}), "Thicker wall")
    assert second.parent == first.id
    shape = cq.importers.importStep(str(prepare_step(second))).val()
    assert shape.isValid() and len(shape.Solids()) == 1
    assert all(
        c.result == "passed"
        for c in second.checks
        if c.name.startswith("Selected access")
    )
    # Remove the new through operation: the older measured recess is still blind.
    plan = compile_plan(a, r)
    damaged = plan.model_copy(
        update={
            "operations": tuple(
                o for o in plan.operations if not o.id.startswith("selected-access")
            )
        }
    )
    bodies, _, cuts = execute(damaged, a, tmp_path / "blind.usda")
    assert any(
        c.result == "failed" and c.name.startswith("Selected access")
        for c in validate(a, r, plan, bodies, cuts)
    )
    with pytest.raises(ValueError, match="locked"):
        patch_requirements(
            r.model_copy(update={"locks": ("access_selections",)}),
            {"access_selections": ()},
        )


def test_unknown_reference_and_removed_contact_rejected(tmp_path):
    a, r, _ = shallow_source(tmp_path)
    with pytest.raises(ValueError, match="no longer"):
        compile_plan(
            a,
            r.model_copy(
                update={"access_selections": (AccessSelection(feature_id="invented"),)}
            ),
        )
    with pytest.raises(
        ValueError, match="Contact|Kernel|material|support|alignment|count"
    ):
        Project(
            a,
            r.model_copy(
                update={
                    "access_selections": (
                        AccessSelection(feature_id="face:" + r.interface_id),
                    )
                }
            ),
        ).generate()


def test_keep_clear_side_face_is_finite(tmp_path):
    from fixture.access import options

    a, r, _ = shallow_source(tmp_path)
    id = next(
        k
        for k, c in options(a, r).items()
        if c["kind"] == "face" and abs(c["outward"][2]) < 0.01
    )
    r = r.model_copy(
        update={
            "access_selections": (
                AccessSelection(feature_id=id, intent="keep_clear", reach=12),
            )
        }
    )
    region = probes(a, r, compile_plan(a, r))[0]
    assert all(s > 0 for s in region.size) and primitive(region).volume() > 0


def test_access_picker_ui_adds_measured_reference(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(
        "fixture.access_controls.picker_component",
        lambda: lambda **kw: SimpleNamespace(picked=None),
    )
    ui = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45
    ).run()
    next(b for b in ui.button if b.label == "Load example").click().run()
    next(
        b for b in ui.button if b.label == "Select openings / keep-clear areas"
    ).click().run()
    p = ui.session_state["project"]
    next(s for s in ui.selectbox if s.label == "Access feature").select(
        "face:" + p.requirements.interface_id
    ).run()
    next(b for b in ui.button if b.label == "Add selected access").click().run()
    assert (
        not ui.exception
        and len(ui.session_state["project"].requirements.access_selections) == 1
    )
