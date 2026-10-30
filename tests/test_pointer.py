"""Optional Node regression for the browser event code; Node is not an app dependency."""

import shutil
import subprocess
from pathlib import Path
import pytest


def test_browser_pointer_regressions():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is only needed for the pointer-event development test")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("test_picker_pointer.mjs"))],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
