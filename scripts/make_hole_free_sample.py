"""Original synthetic specimen, permitted for redistribution; not a product model."""

from pathlib import Path
import cadquery as cq


def main():
    part = cq.Workplane("XY").box(46, 28, 18, centered=(True, True, False))
    part = part.cut(cq.Workplane("XY").box(18, 12, 4).translate((0, 0, 17)))
    output = Path(__file__).resolve().parents[1] / "samples" / "hole_free_housing.step"
    cq.exporters.export(part, str(output))
    print(output)


if __name__ == "__main__":
    main()
