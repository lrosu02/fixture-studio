"""Original synthetic engineering specimens. No manufacturer geometry is used."""

from pathlib import Path
import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]


def make_mixed_holes(out):
    """A permitted source specimen for mixed-size selection; not fixture CAD."""
    part = cq.Workplane("XY").box(60, 40, 6, centered=(True, True, False))
    for x, y, d in [(-20, -12, 3), (20, -12, 3), (-20, 12, 5), (20, 12, 5)]:
        part = part.cut(cq.Workplane("XY").center(x, y).circle(d / 2).extrude(6))
    part = part.union(
        cq.Workplane("XY")
        .workplane(offset=6)
        .box(12, 10, 15, centered=(True, True, False))
    )
    cq.exporters.export(part, str(out / "mixed_hole_sizes.step"))


def main():
    out = ROOT / "samples"
    out.mkdir(exist_ok=True)
    # Asymmetric external geometry makes the mounting end identifiable; these
    # dimensions are test data only and never imported by application code.
    flange = cq.Workplane("XY").box(48, 36, 6, centered=(True, True, False))
    body = cq.Workplane("XY").workplane(offset=6).circle(13).extrude(22)
    motor = flange.union(body).union(
        cq.Workplane("XY").workplane(offset=28).circle(3).extrude(10)
    )
    for x, y in [(-17, -11), (17, -11), (17, 11), (-17, 11)]:
        motor = motor.cut(cq.Workplane("XY").center(x, y).circle(2).extrude(6))
    cq.exporters.export(motor, str(out / "synthetic_motor.step"))
    bracket = cq.Workplane("XY").box(62, 42, 7, centered=(True, True, False))
    for x, y, d in [(-21, -12, 5), (19, -12, 5), (4, 13, 5)]:
        bracket = bracket.cut(cq.Workplane("XY").center(x, y).circle(d / 2).extrude(7))
    bracket = bracket.union(
        cq.Workplane("XY")
        .workplane(offset=7)
        .center(-12, 0)
        .box(10, 12, 18, centered=(True, True, False))
    )
    cq.exporters.export(bracket, str(out / "sensor_bracket.step"))
    moved = motor.val().rotate((0, 0, 0), (1, 2, 3), 47).translate((123, -41, 62))
    cq.exporters.export(moved, str(out / "transformed_motor.step"))
    group = cq.Compound.makeCompound(
        [
            motor.val(),
            cq.Workplane("XY").workplane(offset=38).circle(2).extrude(2).val(),
        ]
    )
    cq.exporters.export(group, str(out / "multi_body.step"))
    ambiguous = (
        cq.Workplane("XY")
        .box(40, 30, 8)
        .faces(">Z")
        .workplane()
        .pushPoints([(-12, -8), (12, -8), (12, 8), (-12, 8)])
        .hole(4)
    )
    cq.exporters.export(ambiguous, str(out / "ambiguous.step"))
    cq.exporters.export(
        cq.Workplane("XY").sphere(10), str(out / "unsupported_sphere.step")
    )
    make_mixed_holes(out)
    print("Wrote seven original synthetic STEP specimens.")


if __name__ == "__main__":
    main()
