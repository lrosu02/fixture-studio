"""Verified native USD serialization with bounded recovery from file-save failures."""

import logging
from pathlib import Path
import re
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


def export_verified(bodies, path, up_axis="Z"):
    """Caller holds the kernel lock. Only verified bytes reach the revision path.

    USD can leave a header-only destination when its internal temporary-file
    rename fails on Windows. A native return alone is not proof of a saved BRep.
    Each retry uses fresh files and copies of the same bodies, never a new plan.
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
                # Publish a separate copy so the USD reader never holds the file
                # being renamed. Replace either succeeds atomically or preserves
                # any existing destination. Read back those exact verified bytes.
                payload = checked.read_bytes()
                pending = Path(folder) / "publish.usda"
                pending.write_bytes(payload)
                pending.replace(path)
                if path.read_bytes() != payload:
                    raise ValueError("Saved CAD bytes differ from the verified export.")
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
    raise CadExportError(
        "CAD could not be saved and verified after three attempts. Retry Generate; "
        "no design dimensions were changed. Details: " + str(last_error)
    ) from last_error
