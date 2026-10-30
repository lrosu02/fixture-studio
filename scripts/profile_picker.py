"""Measure Python mesh serialization work, not network/GPU/end-to-end latency."""

from pathlib import Path
from statistics import median
from time import perf_counter
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixture.project import Project
from fixture.intake import analyze_file
from fixture.hole_picker import picker_geometry
from fixture.viewer import hole_picker_figure
from fixture.picking import HolePicks


def main():
    root = Path(__file__).resolve().parents[1]
    a = (
        Project.load(sys.argv[1]).analysis
        if len(sys.argv) > 1
        else analyze_file(root / "samples" / "mixed_hole_sizes.step")
    )

    def timing(fn):
        values = []
        for _ in range(5):
            start = perf_counter()
            fn()
            values.append((perf_counter() - start) * 1000)
        return median(values)

    before = timing(lambda: hole_picker_figure(a, HolePicks()).to_json())
    picker_geometry(a.source_hash, a)
    after = timing(lambda: picker_geometry(a.source_hash, a))
    report = dict(
        scope="Python figure construction/JSON retrieval only; browser draw, transport and first load excluded",
        uncached_median_ms=before,
        cached_median_ms=after,
        iterations=5,
    )
    print(json.dumps(report, indent=2))
    (root / "artifacts" / "picker-profile.json").write_text(
        json.dumps(report, indent=2)
    )


if __name__ == "__main__":
    main()
