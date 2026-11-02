"""Reproduce the six feature additions with original STEP specimens; no model call."""

from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixture.contracts import Requirements, BaseMount, AccessSelection, HardwareChoice
from fixture.intake import analyze_file
from fixture.project import Project
from fixture.clearance import rear_regions
from fixture.dimensions import edit_dimension
from fixture.step_export import prepare_step
from scripts.reproduce import reproduce

ROOT = Path(__file__).resolve().parents[1]


def common(**kw):
    return Requirements(
        purpose="Synthetic inspection demo",
        quantity=1,
        mounting_confirmed=True,
        surroundings="bolt",
        bench_fastener="M3",
        fabrication="3D printing",
        manufacturing_features=True,
        motion_loads="unknown; geometric concept",
        access="Selected full-through cable opening or open cylinder ends",
        assumptions_accepted=True,
        **kw,
    )


def main():
    output = ROOT / "artifacts" / "features-demo"
    output.mkdir(parents=True, exist_ok=True)
    a = analyze_file(ROOT / "samples/flanged_connector.step")
    face = next(
        i
        for i in a.interfaces
        if i.z[2] > 0.99 and abs(i.origin[2]) < 0.01 and len(i.hole_ids) == 2
    )
    base = analyze_file(ROOT / "samples/mounting_base.step")
    baseface = next(
        i for i in base.interfaces if i.z[2] < -0.99 and len(i.hole_ids) == 4
    )
    profile = rear_regions(a, face, 0.5)[0]
    r = common(
        interface_id=face.id,
        composition="l_bracket",
        nominal_fastener="M3",
        thickness=8,
        margin=20,
        mount_height=60,
        base_mount=BaseMount(
            analysis=base, interface_id=baseface.id, hole_ids=baseface.hole_ids
        ),
        base_offset_y=-60,
        bench_hole_count=4,
        access_selections=(AccessSelection(feature_id="rear:" + profile.id),),
        part_hardware=HardwareChoice(style="counterbore"),
        base_hardware=HardwareChoice(style="countersink"),
    )
    projects = []
    p = Project(a, r)
    first = p.generate()
    p.generate(edit_dimension(r, "thickness", 10), "Stock thickness revised on model")
    projects.append(("connector", p))
    assert p.current.parent == first.id
    a = analyze_file(ROOT / "samples/cylindrical_housing.step")
    face = next(i for i in a.interfaces if i.support_kind == "cylinder")
    r = common(
        interface_id=face.id,
        part_attachment="split_clamp",
        retention_fastener="M3",
        bench_hole_count=4,
        margin=16,
    )
    p = Project(a, r)
    p.generate()
    projects.append(("split-clamp", p))
    a = analyze_file(ROOT / "samples/convex_housing.step")
    face = next(
        i
        for i in a.interfaces
        if i.support_kind == "plane" and i.z[2] > 0.99 and abs(i.origin[2]) < 0.01
    )
    r = common(
        interface_id=face.id, part_attachment="nest", bench_hole_count=4, margin=16
    ).model_copy(update={"fabrication": "Machined stock"})
    p = Project(a, r)
    p.generate()
    projects.append(("contour-nest", p))
    records = []
    for name, p in projects:
        step = prepare_step(p.current)
        (output / (name + ".step")).write_bytes(step.read_bytes())
        archive = output / (name + ".zip")
        archive.write_bytes(p.export())
        reproduce(archive, output / (name + "-reproduced"))
        records.append(
            dict(
                name=name,
                project_id=p.id,
                revision=p.current.id,
                metrics=p.current.metrics,
                failed_checks=[
                    c.name for c in p.current.checks if c.result == "failed"
                ],
            )
        )
        print(name, p.current.summary, flush=True)
    (output / "record.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(output, flush=True)


if __name__ == "__main__":
    main()
