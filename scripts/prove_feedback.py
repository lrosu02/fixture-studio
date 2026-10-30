"""Opt-in real subscription planning + native generation + visual AI feedback."""

from pathlib import Path
import json
import sys
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixture.intake import analyze_file, recommended_interface
from fixture.project import Project
from fixture.subscription import subscription_turn, subscription_review
from fixture.workflow import plan_design, generate_with_feedback
from fixture.planning import missing_questions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--structure", choices=["plate", "l_bracket", "bridge"], default="plate"
    )
    args = parser.parse_args()
    structure = args.structure
    root = Path(__file__).resolve().parents[1]
    analysis = analyze_file(root / "samples" / "sensor_bracket.step")
    project = Project.new(analysis)
    interface = recommended_interface(analysis)
    # Explicit user facts for this permitted synthetic test specimen only.
    brief = (
        f"Design an inspection fixture for two copies of this synthetic sensor bracket. "
        f"I confirm {interface} is the stationary mounting face and all its three measured holes are fastener holes. "
        f"Use a {structure}, two parts in a row, 4.5 mm fixture clearance holes, and clamp it to a bench. "
        "The manufacturing method is 3D printing. Motion and loads are unknown; this is a geometric concept. "
        "Rear tool access is desired but finite access dimensions are unknown. Nominal threads and engagement are unknown. "
        "I accept the visible 6 mm thickness, 8 mm margin and 12 mm gap defaults. Prepare the proposal for review."
    )
    if structure != "plate":
        brief += " Set mount_height to 70 mm and base_depth to 40 mm. For an L-bracket include triangular side ribs. These are explicit synthetic demo choices, not inferred load sizing."
    plan_design(project, subscription_turn, brief, start=True, progress=print)
    if project.error or missing_questions(analysis, project.requirements):
        print(project.error or project.messages[-1]["content"])
        raise RuntimeError(
            "Live planning still needs clarification; no successful generation claimed."
        )
    if project.requirements.composition != structure:
        raise RuntimeError("Live planner did not preserve the requested structure.")
    project.messages.append(
        {
            "role": "user",
            "content": f"I choose the proposed {structure}. Generate it and request AI feedback.",
        }
    )
    generate_with_feedback(
        project,
        subscription_review,
        "ChatGPT subscription (Codex CLI)",
        change=f"Live two-sensor {structure} fixture and AI review",
        progress=print,
    )
    output = root / "demo"
    record = {
        "mode": "Real ChatGPT subscription planning and image-backed review; no Platform API key",
        "project_id": project.id,
        "messages": project.messages,
        "feedback": [f.model_dump() for f in project.feedback],
    }
    prefix = "live-feedback" if structure == "plate" else "live-" + structure
    (output / (prefix + "-record.json")).write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )
    if (
        not project.current
        or not project.feedback
        or project.feedback[-1].outcome == "review_error"
    ):
        raise RuntimeError("Live review incomplete; see the recorded attempt.")
    (output / (prefix + "-export.zip")).write_bytes(project.export())
    print(
        "Live feedback complete:", project.feedback[-1].outcome, project.current.metrics
    )
    print("Saved project:", project.id)


if __name__ == "__main__":
    main()
