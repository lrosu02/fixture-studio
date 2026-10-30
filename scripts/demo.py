"""Reproducible offline geometry demonstration. No live AI calls are made."""

from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixture.intake import analyze_file, recommended_interface
from fixture.contracts import Requirements
from fixture.project import Project
from fixture.agent import offline_turn, apply_action
from fixture.viewer import assembly_figure

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "demo"
    out.mkdir(exist_ok=True)
    a = analyze_file(ROOT / "samples" / "synthetic_motor.step")
    r = Requirements(
        purpose="Synthetic continuous-running fixture concept",
        quantity=6,
        layout="grid",
        columns=3,
        interface_id=recommended_interface(a),
        mounting_confirmed=True,
        clearance_diameter=3.5,
        surroundings="clamp",
        fabrication="Machined solid stock concept",
        material="unknown",
        motion_loads="unknown; no physical performance claim",
        access="rear tool access",
        nominal_fastener="unknown",
        engagement="unknown",
        assumptions_accepted=True,
        unknowns=("material", "motion_loads", "nominal_fastener", "engagement"),
        provenance={"quantity": "user", "clearance_diameter": "user"},
    )
    p = Project.new(a)
    first = p.generate(r, "Six specimens on a common plate")
    revised = apply_action(a, r, offline_turn("more rear access with open supports"))
    second = p.generate(revised, "Open supports for rear tool access")
    archive = out / "example-export.zip"
    archive.write_bytes(p.export())
    figure = assembly_figure(a, revision=second, previous=first)
    figure.write_html(str(out / "assembly.html"), include_plotlyjs=True, full_html=True)
    (out / "results.json").write_text(
        json.dumps(
            {
                "mode": "Offline deterministic demonstration, no live model call",
                "source": a.source_name,
                "first": first.metrics,
                "revision": second.metrics,
                "checks": [c.model_dump() for c in second.checks],
            },
            indent=2,
        )
    )
    print(
        json.dumps(
            {
                "export": str(archive),
                "first": first.metrics,
                "revision": second.metrics,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
