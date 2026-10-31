"""Opt-in real subscription revision/review of the feature demo; no API-key fallback."""

from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixture.project import Project
from fixture.subscription import subscription_turn, subscription_review
from fixture.workflow import plan_design, generate_with_feedback
from fixture.step_export import prepare_step


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root / "artifacts/features-demo"
    record = json.loads((folder / "record.json").read_text(encoding="utf-8"))[0]
    source = Project.load(root / "artifacts" / record["project_id"] / "project.json")
    p = Project(source.analysis, source.requirements)
    p.generate()
    brief = "Revise this existing inspection L-bracket: change only the part screw recesses to 90 degree DIN 7991 countersinks using the built-in M3 profile. Keep the measured base pattern, four base screws, all selected through passages, printing method, dimensions and other requirements unchanged. I accept the existing concept assumptions and unknown loads. Generate the revision and request AI feedback."
    build = plan_design(
        p, subscription_turn, brief, progress=lambda x: print(x, flush=True)
    )
    if not build or p.error:
        raise RuntimeError(p.error or p.messages[-1]["content"])
    assert p.requirements.part_hardware.style == "countersink"
    assert p.requirements.base_mount == source.requirements.base_mount
    assert p.requirements.access_selections == source.requirements.access_selections
    generate_with_feedback(
        p,
        subscription_review,
        "ChatGPT subscription (Codex CLI)",
        change="Live countersink revision",
        progress=lambda x: print(x, flush=True),
    )
    result = {
        "project_id": p.id,
        "messages": p.messages,
        "feedback": [f.model_dump() for f in p.feedback],
    }
    (folder / "live-feedback.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    if (
        not p.feedback
        or p.feedback[-1].outcome in ("review_error", "build_error")
        or p.last_attempt.error
    ):
        raise RuntimeError(
            "Live workflow incomplete; inspect artifacts/features-demo/live-feedback.json"
        )
    prepare_step(p.current)
    (folder / "live-export.zip").write_bytes(p.export())
    print("Live outcome:", p.feedback[-1].outcome, flush=True)


if __name__ == "__main__":
    main()
