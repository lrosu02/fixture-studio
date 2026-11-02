"""Verified native USD serialization with bounded recovery from file-save failures."""

import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import numpy as np
import usd_brep as sm

LOG = logging.getLogger(__name__)
SAVE_ATTEMPTS = 3


class CadExportError(RuntimeError):
    """Storage/serialization failed; changing design dimensions is not a repair."""


def _verify(bodies, path):
    reopened = sm.usd.import_breps(str(path))
    if len(reopened) != len(bodies):
        raise ValueError("BRep round trip changed body count.")
    for original, restored in zip(bodies, reopened):
        if (
            not restored.is_manifold_solid()
            or restored.material_census()["solid_count"] != 1
            or abs(original.volume() - restored.volume())
            > max(0.01, original.volume() * 0.001)
            or not np.allclose(
                original.bounding_box(), restored.bounding_box(), atol=0.01, rtol=0
            )
        ):
            raise ValueError(
                "BRep round trip failed topology, bounds or volume comparison."
            )


def _publish_verified(bodies, data, path, folder, up_axis):
    if not data.startswith("#usda 1.0") or not re.search(
        r"\bdef\s+Brep(?:Array)?\s", data
    ):
        raise ValueError(
            "The CAD exporter left an incomplete file with no BRep geometry."
        )
    if "metersPerUnit" not in data:
        data = data.replace(
            "#usda 1.0",
            '#usda 1.0\n(\n    metersPerUnit = 0.001\n    upAxis = "'
            + up_axis
            + '"\n)',
            1,
        )
    checked = Path(folder) / "checked.usda"
    checked.write_text(data, encoding="utf-8")
    _verify(bodies, checked)
    # The USD reader never opens the file being atomically published.
    payload = checked.read_bytes()
    pending = Path(folder) / "publish.usda"
    pending.write_bytes(payload)
    pending.replace(path)
    if path.read_bytes() != payload:
        raise ValueError("Saved CAD bytes differ from the verified export.")


def _isolated_export(bodies):
    """One recovery with the exact SMLib solids, outside the app's USD runtime.

    Native binary BRep serialization preserves the constructed geometry. A fresh
    hidden process exports those bodies in the OS temporary directory, avoiding
    both project-directory file activity and a long-lived app's USD layer cache.
    The caller verifies the returned USD against the ORIGINAL bodies.
    """
    with tempfile.TemporaryDirectory(
        prefix="fixture-cad-", ignore_cleanup_errors=True
    ) as folder:
        for n, body in enumerate(bodies):
            body.copy().write_to_file(str(Path(folder) / f"body-{n}.brep"), ascii=False)
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(Path(__file__).with_name("cad_export_worker.py")),
                folder,
                str(len(bodies)),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode:
            raise RuntimeError("Isolated native CAD export failed.")
        return (Path(folder) / "native.usda").read_text(encoding="utf-8")


def export_verified(bodies, path, up_axis="Z"):
    """Caller holds the kernel lock. Only verified bytes reach the revision path.

    USD can leave a header-only destination when its internal temporary-file
    rename fails on Windows. A native return alone is not proof of a saved BRep.
    Each retry uses fresh files and copies of the same bodies, never a new plan.
    If in-process retries fail, one isolated native save uses those exact solids.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bodies = list(bodies)
    last_error = None
    for attempt in range(SAVE_ATTEMPTS):
        try:
            # Same filesystem permits atomic publication; unique names also avoid
            # reopening a stale USD layer cached from an earlier failed attempt.
            with tempfile.TemporaryDirectory(
                prefix=".cad-save-", dir=path.parent, ignore_cleanup_errors=True
            ) as folder:
                raw = Path(folder) / "native.usda"
                sm.usd.export_breps([b.copy() for b in bodies], str(raw))
                data = raw.read_text(encoding="utf-8")
                _publish_verified(bodies, data, path, folder, up_axis)
                return
        except (OSError, RuntimeError, ValueError) as error:
            last_error = error
            LOG.warning(
                "CAD save attempt %s/%s failed for %s: %s",
                attempt + 1,
                SAVE_ATTEMPTS,
                path,
                error,
            )
            if attempt + 1 < SAVE_ATTEMPTS:
                time.sleep(0.1 * (attempt + 1))
    try:
        data = _isolated_export(bodies)
        with tempfile.TemporaryDirectory(
            prefix=".cad-save-", dir=path.parent, ignore_cleanup_errors=True
        ) as folder:
            _publish_verified(bodies, data, path, folder, up_axis)
        LOG.info("CAD save recovered using isolated native serialization for %s", path)
        return
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        last_error = error
        LOG.warning("Isolated CAD save failed for %s: %s", path, error)
    raise CadExportError(
        "CAD could not be saved and verified after bounded recovery. Retry Generate; "
        "no design dimensions were changed. Details: " + str(last_error)
    ) from last_error
