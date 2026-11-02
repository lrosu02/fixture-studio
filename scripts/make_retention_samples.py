"""Original cylindrical and convex housing specimens for retention demonstrations."""

from pathlib import Path
import cadquery as cq


def main():
    folder = Path(__file__).resolve().parents[1] / "samples"
    cylinder = cq.Workplane("XY").circle(10).extrude(40)
    housing = (
        cq.Workplane("XY")
        .polyline([(-22, -10), (-12, -16), (16, -13), (24, 2), (13, 16), (-18, 13)])
        .close()
        .extrude(18)
    )
    for name, shape in [
        ("cylindrical_housing.step", cylinder),
        ("convex_housing.step", housing),
    ]:
        cq.exporters.export(shape, str(folder / name))
    connector = cq.Workplane("XY").box(60, 32, 4, centered=(True, True, False))
    connector = connector.cut(
        cq.Workplane("XY").pushPoints([(-24, 0), (24, 0)]).circle(1.5).extrude(4)
    )
    connector = connector.union(
        cq.Workplane("XY")
        .box(22, 16, 20, centered=(True, True, False))
        .translate((0, 0, -20))
    )
    cq.exporters.export(connector, str(folder / "flanged_connector.step"))


if __name__ == "__main__":
    main()
