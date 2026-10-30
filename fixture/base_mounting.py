"""Bounded base-hole placement rules; independent of the uploaded part pattern."""

import numpy as np

BASE_HOLE_PURPOSE = "Surrounding attachment bolt clearance"


def distribute_count(count, regions):
    """Total holes distributed over feet/rails, with at least one per region."""
    if count < regions:
        raise ValueError(
            f"At least {regions} base holes are needed, one per separate foot/rail."
        )
    return tuple(count // regions + (n < count % regions) for n in range(regions))


def spaced(low, high, count, diameter):
    if high < low - 1e-9 or (
        count > 1 and (high - low) / (count - 1) < diameter + 2 - 1e-9
    ):
        raise ValueError(
            "Base holes do not fit with 2 mm edge/ligament clearance. Increase base depth or stock margin, or reduce the base hole count."
        )
    return [(low + high) / 2] if count == 1 else np.linspace(low, high, count).tolist()


def two_lanes(x0, x1, y0, y1, count, diameter, center_odd=False):
    """Paired outer lanes, optionally reserving an odd hole for the center.

    Center placement is enabled only on continuous L-bracket feet. On plates
    or separate rails it could cross the part's mounting/contact region.
    The previous unequal-lane rule remains available for version-5 exports.
    """
    if count == 1:
        return [((x0 + x1) / 2, spaced(y0, y1, 1, diameter)[0])]
    if x1 - x0 < diameter + 2:
        raise ValueError("Increase stock margin/width for base-hole separation.")
    centered = center_odd and count % 2 == 1
    counts = distribute_count(count - int(centered), 2)
    points = [
        (x, y) for x, n in zip((x0, x1), counts) for y in spaced(y0, y1, n, diameter)
    ]
    if centered:
        middle = ((x0 + x1) / 2, (y0 + y1) / 2)
        if any(
            np.hypot(x - middle[0], y - middle[1]) < diameter + 2 - 1e-9
            for x, y in points
        ):
            raise ValueError(
                "Centered base hole does not fit with 2 mm ligament clearance. Increase base width/margin or depth."
            )
        points.append(middle)
    return points


def expected_count(requirements, plan):
    if requirements.base_mount is not None:
        return len(requirements.base_mount.hole_ids)
    if requirements.surroundings != "bolt":
        return 0
    if plan.version >= 5 and requirements.bench_hole_count is not None:
        return requirements.bench_hole_count
    if plan.composition == "l_bracket":
        return 2
    if plan.composition == "bridge":
        return 4
    return 2 * sum(op.kind == "stock" for op in plan.operations)
