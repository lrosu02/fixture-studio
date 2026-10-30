from types import SimpleNamespace
from pathlib import Path
import subprocess
import pytest
from fixture.agent import Action, Changes
from fixture.subscription import subscription_turn
from tests.test_geometry import ready


def test_subscription_has_no_api_key_and_disables_execution(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret-not-real")
    monkeypatch.setenv("FIXTURE_CODEX_PATH", "codex.exe")
    a, r = ready()
    action = Action(
        action="clarify",
        changes=Changes(),
        questions=("What is the load?",),
        highlight_ids=(),
        explanation="Unknown loads retained",
    )

    def runner(command, **kwargs):
        assert "OPENAI_API_KEY" not in kwargs["env"]
        if command[1:] == ["login", "status"]:
            return SimpleNamespace(
                returncode=0, stdout="Logged in using ChatGPT", stderr=""
            )
        assert "--sandbox" in command and "read-only" in command
        assert (
            "features.shell_tool=false" in command and "features.apps=false" in command
        )
        assert "--ignore-user-config" in command and "--ephemeral" in command
        assert 'forced_login_method="chatgpt"' in command
        Path(command[command.index("--output-last-message") + 1]).write_text(
            action.model_dump_json()
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    assert subscription_turn(a, r, [], runner=runner) == action


def test_subscription_rejects_api_login(monkeypatch):
    monkeypatch.setenv("FIXTURE_CODEX_PATH", "codex.exe")
    a, r = ready()
    with pytest.raises(ValueError, match="subscription"):
        subscription_turn(
            a,
            r,
            [],
            runner=lambda *args, **kwargs: SimpleNamespace(
                returncode=0, stdout="Logged in using an API key", stderr=""
            ),
        )


def test_subscription_timeout(monkeypatch):
    monkeypatch.setenv("FIXTURE_CODEX_PATH", "codex.exe")
    a, r = ready()

    def runner(command, **kwargs):
        if command[1:] == ["login", "status"]:
            return SimpleNamespace(
                returncode=0, stdout="Logged in using ChatGPT", stderr=""
            )
        raise subprocess.TimeoutExpired(command, 120)

    with pytest.raises(TimeoutError):
        subscription_turn(a, r, [], runner=runner)
