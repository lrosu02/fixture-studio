"""Repeatable sheet assembly + thickness/joint revision using the synthetic sample."""

from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fixture.contracts import Requirements
from fixture.intake import analyze_file, recommended_interface
from fixture.manufacturing import SHEET_METAL
from fixture.planning import patch_requirements
from fixture.project import Project
from fixture.step_export import prepare_step


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bent",
        action="store_true",
        help="Form one wall/base blank with a real 90-degree bend and fitted welded ribs",
    )
    args = parser.parse_args()
    analysis = analyze_file(ROOT / "samples" / "synthetic_motor.step")
    requirements = Requirements(
        purpose="Sheet assembly demonstration",
        quantity=1,
        interface_id=recommended_interface(analysis),
        mounting_confirmed=True,
        nominal_fastener="M3",
        composition="l_bracket",
        thickness=3,
        mount_height=70,
        base_depth=40,
        surroundings="bolt",
        bench_fastener="M3",
        bench_hole_count=4,
        fabrication=SHEET_METAL,
        sheet_construction="bent_weld" if args.bent else "cut_weld",
        motion_loads="Static inspection; strength not evaluated",
        access="Rear access",
        assumptions_accepted=True,
    )
    project = Project(analysis, requirements)
    initial = project.generate(change="3 mm sheet L-bracket with locating tabs")
    prepare_step(initial)
    revision = project.generate(
        patch_requirements(
            requirements,
            {
                "thickness": 4,
                "sheet_tab_count": 3,
                "sheet_root_gap": 0.1,
                "base_depth": 50,
            },
        ),
        "4 mm sheet, three tabs per base joint and 0.1 mm root gap",
    )
    step = prepare_step(revision)
    archive = ROOT / "artifacts" / project.id / "sheet-metal-demo.zip"
    archive.write_bytes(project.export(False))
    print(f"Project: {archive.parent / 'project.json'}")
    print(f"STEP: {step}")
    print(f"Bundle: {archive}")
    print(
        f"Panels: {len(revision.plan.sheet_panels)}; joints: {len(revision.plan.sheet_joints)}; failed checks: {sum(c.result == 'failed' for c in revision.checks)}"
    )


if __name__ == "__main__":
    main()
