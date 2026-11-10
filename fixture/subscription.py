"""Supported Codex CLI adapter using the user's existing ChatGPT sign-in.

No credential extraction, app UI automation or private HTTP endpoint. Each
turn uses an ephemeral, read-only CLI process and a schema-constrained result.
"""

from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
from .agent import Action, SYSTEM, strict_schema, planner_context
from .contracts import DesignReview
from .review import REVIEW_SYSTEM

ROOT = Path(__file__).resolve().parents[1]


def executable():
    return os.environ.get("FIXTURE_CODEX_PATH") or shutil.which("codex")


def subscription_turn(
    analysis,
    requirements,
    messages,
    current=None,
    runner=subprocess.run,
    workflow_state=None,
):
    return _subscription_decision(
        Action,
        SYSTEM,
        planner_context(analysis, requirements, current, workflow_state),
        messages,
        (),
        runner,
    )


def subscription_review(context, messages, images=(), runner=subprocess.run):
    return _subscription_decision(
        DesignReview, REVIEW_SYSTEM, context, messages, images, runner
    )


def _subscription_decision(
    response_schema, instruction, context, messages, images, runner
):
    exe = executable()
    if not exe:
        raise ValueError(
            "Codex CLI not found. Install it or set FIXTURE_CODEX_PATH, then run codex login with ChatGPT."
        )
    env = dict(os.environ)
    # This provider must not silently charge a Platform API key.
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        env.pop(key, None)
    flags = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "env": env,
        "creationflags": subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    }
    status = runner([exe, "login", "status"], timeout=15, **flags)
    if (
        status.returncode
        or "logged in using chatgpt" not in (status.stdout + status.stderr).lower()
    ):
        raise ValueError(
            "This backend requires ChatGPT subscription sign-in. Run codex login in your own terminal; API-key login is not used."
        )
    scratch = ROOT / "artifacts" / "planner"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as temp:
        folder = Path(temp)
        schema = folder / "schema.json"
        answer = folder / "answer.json"
        schema.write_text(
            json.dumps(strict_schema(response_schema.model_json_schema())),
            encoding="utf-8",
        )
        instruction = instruction.replace(
            "Call design_action once with a bounded decision.",
            "Return exactly one JSON design_action object matching the supplied output schema. No tool calls.",
        ).replace(
            "Call design_review once.",
            "Return exactly one JSON object matching the supplied output schema. No tool calls.",
        )
        prompt = (
            instruction
            + "\n\nApplication records:\n"
            + json.dumps(context)
            + "\n\nConversation:\n"
            + json.dumps(messages[-20:])
        )
        cmd = [
            exe,
            "-a",
            "never",
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--cd",
            str(folder),
            "--output-schema",
            str(schema),
            "--output-last-message",
            str(answer),
            "--json",
            "--color",
            "never",
        ]
        for feature in (
            "shell_tool",
            "apps",
            "plugins",
            "multi_agent",
            "computer_use",
            "browser_use",
            "image_generation",
            "view_image",
            "code_mode",
            "code_mode_host",
            "hooks",
            "memories",
            "goals",
            "sleep_tool",
        ):
            cmd.extend(["-c", f"features.{feature}=false"])
        for value in (
            'web_search="disabled"',
            "skills.bundled.enabled=false",
            "skills.include_instructions=false",
            "project_doc_max_bytes=0",
            'forced_login_method="chatgpt"',
        ):
            cmd.extend(["-c", value])
        if os.getenv("FIXTURE_CODEX_MODEL"):
            cmd.extend(["--model", os.environ["FIXTURE_CODEX_MODEL"]])
        for image in images:
            cmd.extend(["--image", str(Path(image).resolve())])
        cmd.append("-")
        try:
            result = runner(cmd, input=prompt, timeout=120, **flags)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(
                "Subscription planner timed out after 120 seconds. Previous design retained; retry or use controls."
            ) from error
        if result.returncode or not answer.is_file():
            # Keep credentials/private diagnostic logs out of the UI.
            raise RuntimeError(
                "Codex planning failed. Check ChatGPT sign-in, subscription availability and CLI version. Previous design retained."
            )
        return response_schema.model_validate_json(answer.read_text(encoding="utf-8"))
