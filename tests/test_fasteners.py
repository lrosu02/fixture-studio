import io
import json
import zipfile

import pytest

from fixture.fasteners import resolve_clearances, nominal_size, SOURCE
from fixture.planning import compile_plan, missing_questions, patch_requirements
from fixture.executor import execute
from fixture.validation import validate
from fixture.project import Project
from tests.test_geometry import ready


def test_proposed_metric_inch_and_per_hole_choices(tmp_path):
    from fixture.contracts import HoleFastenerChoice
    from fixture.fasteners import proposed_screw_sizes
    from fixture.intake import selected_interface

    assert proposed_screw_sizes(3.0) == ["M3", "#4"]
    a, r = ready("mixed_hole_sizes.step", clearance_diameter=None)
    interface = selected_interface(a, r)
    small = tuple(
        h for h, d in zip(interface.hole_ids, interface.diameters) if abs(d - 3) < 0.01
    )
    r = patch_requirements(
        r, {"hole_fasteners": (HoleFastenerChoice(hole_ids=small, nominal="#4"),)}
    )
    records = resolve_clearances(a, r)
    assert {c.diameter for c in records if c.feature_id in small} == {3.2639}
    assert {c.diameter for c in records if c.feature_id not in small} == {5.5}
    assert {c.standard for c in records if c.feature_id in small} == {
        "ACF inch-series chart"
    }
    plan = compile_plan(a, r)
    bodies, _, cuts = execute(plan, a, tmp_path / "imperial.usda")
    assert not [c for c in validate(a, r, plan, bodies, cuts) if c.result == "failed"]
    automatic = patch_requirements(
        r, {"hole_fasteners": (HoleFastenerChoice(hole_ids=small),)}
    )
    assert {
        c.nominal for c in resolve_clearances(a, automatic) if c.feature_id in small
    } == {"M3"}
    custom = patch_requirements(
        r,
        {
            "hole_fasteners": (
                HoleFastenerChoice(
                    hole_ids=small, nominal="custom pin", clearance_diameter=3.7
                ),
            )
        },
    )
    assert {
        c.diameter for c in resolve_clearances(a, custom) if c.feature_id in small
    } == {3.7}


def test_screw_choice_cannot_bypass_existing_locks():
    from fixture.contracts import HoleFastenerChoice
    from fixture.intake import selected_interface

    a, r = ready(nominal_fastener="M3", clearance_diameter=3.2)
    holes = selected_interface(a, r).hole_ids
    for key, nominal, diameter in [
        ("nominal_fastener", "#4", None),
        ("clearance_diameter", "M3", 3.7),
        ("hole_fasteners", "#4", None),
    ]:
        with pytest.raises(ValueError, match="locked"):
            patch_requirements(
                r.model_copy(update={"locks": (key,)}),
                {
                    "hole_fasteners": (
                        HoleFastenerChoice(
                            hole_ids=holes, nominal=nominal, clearance_diameter=diameter
                        ),
                    )
                },
            )


@pytest.mark.parametrize(
    "fit,diameter", [("fine", 3.2), ("medium", 3.4), ("coarse", 3.6)]
)
def test_standard_defaults_without_clearance_questions(fit, diameter):
    a, r = ready(
        clearance_diameter=None,
        nominal_fastener="M3",
        surroundings="bolt",
        clearance_fit=fit,
    )
    assert missing_questions(a, r) == []
    plan = compile_plan(a, r)
    assert plan.version == 13
    assert {c.diameter for c in plan.clearances} == {diameter}
    assert all(
        c.standard == "ISO 273" and c.source_url == SOURCE and c.origin == "derived"
        for c in plan.clearances
    )
    assert r.clearance_diameter is None and r.bench_hole_diameter is None
    assert {op.diameter for op in plan.operations if op.kind == "mount"} == {diameter}
    assert {
        op.size[0]
        for op in plan.operations
        if op.purpose == "Surrounding attachment bolt clearance"
    } == {diameter}


def test_mixed_sizes_native_bores_and_saved_provenance(tmp_path):
    a, r = ready("mixed_hole_sizes.step", clearance_diameter=None)
    plan = compile_plan(a, r)
    assert sorted(c.diameter for c in plan.clearances) == [3.4, 3.4, 5.5, 5.5]
    assert all(c.basis.startswith("Assumed") for c in plan.clearances)
    assert r.nominal_fastener is None
    bodies, _, cuts = execute(plan, a, tmp_path / "mixed.usda")
    assert not [c for c in validate(a, r, plan, bodies, cuts) if c.result == "failed"]
    changed = [dict(c) for c in cuts]
    changed[0]["diameter"] += 0.2
    assert (
        next(
            c
            for c in validate(a, r, plan, bodies, changed)
            if c.name == "Clearance selection"
        ).result
        == "failed"
    )
    p = Project(a, r)
    p.generate()
    with zipfile.ZipFile(io.BytesIO(p.export())) as archive:
        records = json.loads(archive.read("fastener-clearances.json"))
        assert {c["nominal"] for c in records} == {"M3", "M5"}
        assert all(c["source_verified"] == "2026-10-30" for c in records)
    from scripts.reproduce import reproduce

    bundle = tmp_path / "mixed.zip"
    bundle.write_bytes(p.export())
    reproduce(bundle, tmp_path / "reproduced")


def test_explicit_clearances_and_locks_take_priority():
    a, r = ready(
        nominal_fastener="M3",
        clearance_diameter=3.2,
        surroundings="bolt",
        bench_hole_diameter=3.2,
    )
    records = resolve_clearances(a, r)
    assert {c.diameter for c in records} == {3.2}
    assert all(c.origin == "user" and c.standard is None for c in records)
    updated = patch_requirements(
        r, {"nominal_fastener": "M4", "clearance_fit": "coarse"}
    )
    assert {c.diameter for c in resolve_clearances(a, updated)} == {3.2}
    for key, value in [
        ("clearance_fit", "fine"),
        ("clearance_diameter", None),
        ("nominal_fastener", "M4"),
    ]:
        with pytest.raises(ValueError, match="locked"):
            patch_requirements(r.model_copy(update={"locks": (key,)}), {key: value})


def test_separate_base_size_and_unsupported_nominals():
    a, r = ready(
        clearance_diameter=None,
        nominal_fastener="M3",
        surroundings="bolt",
        bench_fastener="M6",
    )
    records = resolve_clearances(a, r)
    assert records[-1].diameter == 6.6 and records[0].diameter == 3.4
    assert nominal_size("M3×0.5") == 3
    for text in ["#6-32", "M7", "M0.8"]:
        with pytest.raises(ValueError, match="outside"):
            nominal_size(text)
    # A custom, non-metric fastener remains usable with explicit dimensions.
    custom = r.model_copy(
        update={
            "nominal_fastener": "#6-32",
            "clearance_diameter": 3.8,
            "bench_hole_diameter": 4.1,
        }
    )
    assert resolve_clearances(a, custom)[0].diameter == 3.8
    # Tiny openings must not be silently assigned a larger unsupported screw.
    index = next(n for n, i in enumerate(a.interfaces) if i.id == r.interface_id)
    interfaces = list(a.interfaces)
    interfaces[index] = interfaces[index].model_copy(
        update={"diameters": tuple(1.0 for _ in interfaces[index].diameters)}
    )
    with pytest.raises(ValueError, match="below"):
        resolve_clearances(
            a.model_copy(update={"interfaces": tuple(interfaces)}),
            r.model_copy(update={"nominal_fastener": None}),
        )


def test_native_base_clearance_validation_and_historical_compilers(tmp_path):
    a, r = ready(
        composition="l_bracket",
        surroundings="bolt",
        nominal_fastener="M3",
        clearance_diameter=None,
    )
    plan = compile_plan(a, r)
    bodies, _, cuts = execute(plan, a, tmp_path / "bracket.usda")
    assert all(c.result != "failed" for c in validate(a, r, plan, bodies, cuts))
    operations = tuple(
        op.model_copy(update={"size": (4.0, 4.0, op.size[2])})
        if op.purpose == "Surrounding attachment bolt clearance"
        else op
        for op in plan.operations
    )
    changed = plan.model_copy(update={"operations": operations})
    assert (
        next(
            c
            for c in validate(a, r, changed, bodies, cuts)
            if c.name == "Clearance selection"
        ).result
        == "failed"
    )
    legacy = r.model_copy(
        update={"clearance_diameter": 3.2, "bench_hole_diameter": 3.2}
    )
    for version in (1, 2):
        old = compile_plan(a, legacy, compiler_version=version)
        assert old.version == version and old.clearances == ()
