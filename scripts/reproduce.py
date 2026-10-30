"""Rebuild exported fixture CAD from bounded records; never execute archive code."""

from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixture.contracts import Analysis, Plan, Requirements
from fixture.planning import compile_plan
from fixture.executor import execute
from fixture.validation import validate


def reproduce(archive, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:

        def read(name):
            if z.getinfo(name).file_size > 50_000_000:
                raise ValueError("Record exceeds 50 MB.")
            return z.read(name)

        a = Analysis.model_validate_json(read("source-analysis.json"))
        r = Requirements.model_validate_json(read("requirements.json"))
        saved = Plan.model_validate_json(read("plan.json"))
    plan = compile_plan(a, r, compiler_version=saved.version)
    if plan != saved:
        raise ValueError(
            "Saved plan differs from deterministic compilation; review the record version."
        )
    bodies, meshes, cuts = execute(plan, a, out / "fixture.usda")
    checks = validate(a, r, plan, bodies, cuts)
    if any(c.result == "failed" for c in checks):
        raise ValueError("Reproduced geometry failed checks.")
    print(
        f"Rebuilt {len(bodies)} real SMLib BReps; volume {sum(b.volume() for b in bodies.values()):.6f} mm³"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/reproduce.py export.zip output-folder")
    reproduce(sys.argv[1], sys.argv[2])
