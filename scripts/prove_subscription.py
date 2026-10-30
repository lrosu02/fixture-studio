"""A real subscription-backed planner call; no paid API-key fallback."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixture.intake import analyze_file, recommended_interface
from fixture.contracts import Requirements
from fixture.subscription import subscription_turn
from fixture.agent import apply_action
from fixture.project import Project

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    a = analyze_file(root / "samples" / "synthetic_motor.step")
    r = Requirements(interface_id=recommended_interface(a))
    messages = [
        {
            "role": "user",
            "content": "I want a fixture for six of these parts for continuous running. Keep it accessible and give it a clean appearance.",
        }
    ]
    action = subscription_turn(a, r, messages)
    (root / "artifacts" / "subscription-proof.json").write_text(
        action.model_dump_json(indent=2)
    )
    print(action.model_dump_json(indent=2))
    if "--full" in sys.argv:
        messages.append(
            {
                "role": "assistant",
                "content": action.explanation + " " + str(action.questions),
            }
        )
        r = apply_action(a, r, action)
        messages.append(
            {
                "role": "user",
                "content": f"For this synthetic test specimen I confirm {r.interface_id} is the stationary mounting face and all four highlighted holes are fastener holes. Use 3.5 mm fixture clearance holes. Hold six parts in a grid with three columns on a common plate. Clamp the fixture to the bench. Fabrication is machined solid stock, material unknown. Motion, loads, threads and engagement remain unknown; this is only a geometric concept, with no physical performance claim. Access needs are rear tool access, with finite tool dimensions unknown. I accept the visible concept defaults for thickness, margin and gap. Generate this plate now.",
            }
        )
        second = subscription_turn(a, r, messages)
        r = apply_action(a, r, second)
        p = Project.new(a)
        first = p.generate(r, "Live subscription: six on a plate")
        messages.append({"role": "assistant", "content": first.summary})
        messages.append(
            {
                "role": "user",
                "content": "Revise it to open parallel supports for more rear tool access and less material. Preserve all measured mounting holes, six instances and the three-column grid. Generate the revised fixture.",
            }
        )
        third = subscription_turn(a, r, messages, first)
        updated = apply_action(a, r, third)
        final = p.generate(updated, "Live subscription: open support revision")
        output = root / "demo"
        output.mkdir(exist_ok=True)
        (output / "live-subscription-export.zip").write_bytes(p.export())
        import json

        (output / "live-subscription-record.json").write_text(
            json.dumps(
                {
                    "mode": "Real Codex CLI calls using ChatGPT sign-in; no API key",
                    "messages": messages,
                    "actions": [
                        action.model_dump(),
                        second.model_dump(),
                        third.model_dump(),
                    ],
                    "first": first.metrics,
                    "revision": final.metrics,
                },
                indent=2,
            )
        )
        print("Live sequence passed:", final.metrics)
