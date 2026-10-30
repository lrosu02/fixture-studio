from pathlib import Path
import sys

import pytest
import usd_brep as sm

from fixture import cad_io
from fixture.project import Project
from fixture.workflow import generate_with_feedback
from tests.test_geometry import ready, ROOT


@pytest.mark.parametrize("failure", ["header", "native_error"])
def test_transient_export_failure_retries_same_geometry(tmp_path, monkeypatch, failure):
    body = sm.primitives.create_box((0, 0, 0), 10, 12, 8)
    target = tmp_path / "fixture.usda"
    target.write_bytes(b"previous file must not be replaced before verification")
    old = target.read_bytes()
    native = sm.usd.export_breps
    paths = []

    def flaky(bodies, filename):
        paths.append(filename)
        assert target.read_bytes() == old
        assert bodies[0].volume() == pytest.approx(960)
        if len(paths) == 1:
            if failure == "native_error":
                raise RuntimeError(
                    "SmApiUsdExportBreps failed: simulated Windows rename failure"
                )
            # Observed failure: native call returns, but only a USD header exists.
            Path(filename).write_text("#usda 1.0\n")
        else:
            native(bodies, filename)

    monkeypatch.setattr(sm.usd, "export_breps", flaky)
    cad_io.export_verified([body], target, "Y")
    assert len(paths) == len(set(paths)) == 2
    assert 'upAxis = "Y"' in target.read_text()
    assert "metersPerUnit = 0.001" in target.read_text()
    (restored,) = sm.usd.import_breps(str(target))
    assert restored.volume() == pytest.approx(960)


def test_round_trip_mismatch_never_publishes(tmp_path, monkeypatch):
    target = tmp_path / "fixture.usda"
    cad_io.export_verified([sm.primitives.create_box((0, 0, 0), 2, 3, 4)], target)
    previous = target.read_bytes()
    native = sm.usd.export_breps
    calls = []

    def corrupt(bodies, filename):
        calls.append(filename)
        native([sm.primitives.create_box((0, 0, 0), 1, 1, 1)], filename)

    monkeypatch.setattr(sm.usd, "export_breps", corrupt)
    with pytest.raises(cad_io.CadExportError, match="round trip"):
        cad_io.export_verified([sm.primitives.create_box((0, 0, 0), 2, 3, 4)], target)
    assert len(calls) == 3 and target.read_bytes() == previous


def test_save_failure_keeps_last_revision_and_skips_ai_repairs(monkeypatch):
    a, r = ready()
    p = Project(a, r)
    previous = p.generate()
    previous_bytes = Path(previous.artifact).read_bytes()
    exports = []

    def incomplete(bodies, filename):
        exports.append(filename)
        Path(filename).write_text("#usda 1.0\n")

    def reviewer(*args):
        pytest.fail("A storage failure must not request AI dimensional repair.")

    monkeypatch.setattr(sm.usd, "export_breps", incomplete)
    result = generate_with_feedback(p, reviewer, "Test double")
    assert result.id == previous.id and len(p.revisions) == 1
    assert (
        p.requirements == r and Path(previous.artifact).read_bytes() == previous_bytes
    )
    assert len(exports) == 3
    assert p.feedback[-1].outcome == "build_error"
    assert p.feedback[-1].build.failure_kind == "cad_export"
    assert p.feedback[-1].review is None and p.feedback[-1].build.revision_id is None
    restored = Project.load(ROOT / "artifacts" / p.id / "project.json")
    assert restored.current.id == previous.id and restored.feedback == p.feedback


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file-sharing semantics")
def test_actual_windows_rename_lock_recovers(tmp_path, monkeypatch):
    import ctypes
    from ctypes import wintypes

    target = (tmp_path / "fixture.usda").resolve()
    target.write_bytes(b"previous")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    # Share read/write but not delete: a real Windows atomic rename denial.
    handle = kernel.CreateFileW(str(target), 0x80000000, 3, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    waits = []

    def release_on_retry(delay):
        nonlocal handle
        assert target.read_bytes() == b"previous"
        waits.append(delay)
        kernel.CloseHandle(handle)
        handle = None

    monkeypatch.setattr(cad_io.time, "sleep", release_on_retry)
    try:
        cad_io.export_verified(
            [sm.primitives.create_box((0, 0, 0), 10, 10, 10)], target
        )
    finally:
        if handle is not None:
            kernel.CloseHandle(handle)
    assert waits == [0.1]
    (restored,) = sm.usd.import_breps(str(target))
    assert restored.volume() == pytest.approx(1000)
