"""Click-placed, round through openings in a generated fixture.

Picking is mesh-only. SMLib constructs and checks the actual cuts on rebuild.
Positions are absolute in the fixture frame, and are not copied per source part.
Changing fixture type retains opening sizes but requires new surface picks.
"""

import math
from uuid import uuid4

import numpy as np

from .contracts import FixtureOpening, Operation, Plan, MM_TOL
from .operation_bounds import bounds
from .planning import patch_requirements

PREFIX = "fixture-opening-"
RIM = 0.5  # Geometric edge land only; no strength or fabrication qualification.


def resolve_pick(revision, event):
    if revision is None or not isinstance(event, dict):
        raise ValueError("Generate a fixture before placing an opening.")
    if event.get("revision_id") != revision.id:
        raise ValueError(
            "This click belongs to an older fixture. Click the current design."
        )
    body, index = event.get("body"), event.get("triangle")
    if body not in revision.meshes or type(index) is not int:
        raise ValueError("Click a generated fixture surface.")
    mesh = revision.meshes[body]
    if not 0 <= index < len(mesh.triangles):
        raise ValueError("The selected triangle does not belong to this fixture.")
    point = np.asarray(event.get("point"), dtype=float)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError("Opening position must be a finite 3D point.")
    a, b, c = np.asarray(mesh.vertices)[list(mesh.triangles[index])]
    normal = np.cross(b - a, c - a)
    length = np.linalg.norm(normal)
    if length < 1e-9:
        raise ValueError("Choose a flat surface with a measurable area.")
    normal /= length
    axis = int(np.argmax(np.abs(normal)))
    if abs(normal[axis]) < 1 - 1e-8:
        raise ValueError(
            "Choose a flat wall, base or rib side; curved and sloped surfaces are not supported yet."
        )
    if abs(np.dot(point - a, normal)) > 0.01:
        raise ValueError("The opening point is not on the clicked surface.")
    uv = np.linalg.lstsq(np.column_stack((b - a, c - a)), point - a, rcond=None)[0]
    if min(uv) < -1e-5 or sum(uv) > 1 + 1e-5:
        raise ValueError("The opening point lies outside the clicked triangle.")
    return dict(body=body, center=tuple(float(x) for x in point), axis="xyz"[axis])


def _current(project):
    if project.current is None:
        raise ValueError("Generate the first fixture before adding openings.")
    if project.requirements.interface_id != project.current.requirements.interface_id:
        raise ValueError("The mounting frame changed. Rebuild before placing openings.")
    if project.requirements.composition != project.current.requirements.composition:
        raise ValueError("Generate the new fixture type before placing its openings.")


def opening_candidate(project, event, diameter, opening_id=None):
    _current(project)
    picked = resolve_pick(project.current, event)
    existing = project.requirements.fixture_openings
    if opening_id is not None and opening_id not in {o.id for o in existing}:
        raise ValueError("This saved opening no longer exists.")
    opening = FixtureOpening(
        id=opening_id or uuid4().hex[:12], diameter=diameter, **picked
    )
    values = (
        tuple(opening if o.id == opening.id else o for o in existing)
        if opening_id is not None
        else existing + (opening,)
    )
    return patch_requirements(project.requirements, {"fixture_openings": values})


def resize_opening(project, opening_id, diameter):
    _current(project)
    if opening_id not in {o.id for o in project.requirements.fixture_openings}:
        raise ValueError("This saved opening no longer exists.")
    if next(
        o for o in project.requirements.fixture_openings if o.id == opening_id
    ).needs_placement:
        raise ValueError("Place this opening on the new fixture before resizing it.")
    values = tuple(
        FixtureOpening.model_validate({**o.model_dump(), "diameter": diameter})
        if o.id == opening_id
        else o
        for o in project.requirements.fixture_openings
    )
    return patch_requirements(project.requirements, {"fixture_openings": values})


def remove_opening(project, opening_id):
    # Removing saved intent does not require a matching preview surface.
    if project.current is None:
        raise ValueError("Generate the first fixture before editing openings.")
    if opening_id not in {o.id for o in project.requirements.fixture_openings}:
        raise ValueError("This saved opening no longer exists.")
    return patch_requirements(
        project.requirements,
        {
            "fixture_openings": tuple(
                o for o in project.requirements.fixture_openings if o.id != opening_id
            )
        },
    )


def opening_tools(r, plan):
    if len({o.id for o in r.fixture_openings}) != len(r.fixture_openings):
        raise ValueError("Fixture opening IDs must be unique.")
    placed = tuple(o for o in r.fixture_openings if not o.needs_placement)
    if not placed:
        return ()
    bodies = set()
    stock_bounds = []
    for op in plan.operations:
        if op.kind in ("stock", "support"):
            bodies.add(op.body)
            stock_bounds.append(bounds(op))
        if op.kind == "combine":
            bodies.remove(op.other)
    low = np.min([b[0] for b in stock_bounds], axis=0) - 1
    high = np.max([b[1] for b in stock_bounds], axis=0) + 1
    tools = []
    for opening in placed:
        if opening.body not in bodies:
            raise ValueError(
                "An opening's fixture part no longer exists. Remove or reposition the opening."
            )
        k = "xyz".index(opening.axis)
        origin = list(opening.center)
        origin[k] = float(low[k])
        tools.append(
            Operation(
                id=PREFIX + opening.id,
                kind="relief",
                target=opening.body,
                shape="cylinder",
                axis=opening.axis,
                origin=tuple(origin),
                size=(opening.diameter, opening.diameter, float(high[k] - low[k])),
                purpose="User-placed through opening: " + opening.id,
                provenance={"position": "user", "diameter": "user", "depth": "derived"},
            )
        )
    return tuple(tools)


def add_openings(r, plan):
    if not r.fixture_openings:
        return plan
    if plan.version < 14:
        raise ValueError("User-placed openings require compiler version 14.")
    pending = sum(o.needs_placement for o in r.fixture_openings)
    if pending and plan.version < 15:
        raise ValueError("Openings awaiting placement require compiler version 15.")
    operations = list(plan.operations)
    for tool in opening_tools(r, plan):
        operations.append(tool.model_copy(update={"depends_on": (operations[-1].id,)}))
    return Plan.model_validate(
        {
            **plan.model_dump(),
            "operations": operations,
            "parameters": {
                **plan.parameters,
                "fixture_opening_count": len(r.fixture_openings) - pending,
                **({"pending_fixture_opening_count": pending} if pending else {}),
            },
        }
    )


def check_cut(body, op):
    """Reject misses, edge breakouts, overlapping holes and inadequate edge land."""
    import usd_brep as sm
    from .executor import primitive

    removed = sm.booleans.boolean_intersection(body.copy(), primitive(op))
    volume = abs(removed.volume())
    if volume <= MM_TOL:
        raise ValueError(
            "Opening misses fixture material. Pick a solid area of the current fixture."
        )
    low, high = np.asarray(removed.bounding_box())
    k = "xyz".index(op.axis)
    thickness = high[k] - low[k]
    expected = math.pi * (op.size[0] / 2) ** 2 * thickness
    if abs(volume - expected) > max(0.02, expected * 0.001):
        raise ValueError(
            "Opening crosses an edge, existing hole or irregular section. Move it onto a clear flat area or reduce its diameter."
        )
    # A tessellation chord can have an axis-aligned normal on a curved wall.
    # Verify both ends against native surfaces rather than trusting that triangle.
    radial = [n for n in range(3) if n != k]
    for end in (low[k], high[k]):
        for angle in np.linspace(0, 2 * math.pi, 12, endpoint=False):
            point = list(op.origin)
            point[k] = float(end)
            point[radial[0]] += 0.45 * op.size[0] * math.cos(angle)
            point[radial[1]] += 0.45 * op.size[0] * math.sin(angle)
            if sm.get_closest_point(body, tuple(point))[1] > 1e-4:
                raise ValueError(
                    "Opening entry and exit must be flat surfaces perpendicular to its axis."
                )
    origin = list(op.origin)
    inset = min(0.01, thickness / 10)
    origin[k] = float(low[k] + inset)
    outer = op.model_copy(
        update={
            "origin": tuple(origin),
            "size": (
                op.size[0] + 2 * RIM,
                op.size[0] + 2 * RIM,
                float(thickness - 2 * inset),
            ),
        }
    )
    ring = sm.booleans.boolean_difference(primitive(outer), primitive(op))
    missing = abs(sm.booleans.boolean_difference(ring, body.copy()).volume())
    if missing > MM_TOL:
        raise ValueError(
            "Opening needs at least 0.5 mm of material around its rim. Move it away from edges/other holes or reduce its diameter."
        )


def validate_openings(r, plan, bodies, add):
    import usd_brep as sm
    from .executor import primitive

    pending = tuple(o for o in r.fixture_openings if o.needs_placement)
    if pending:
        add(
            "Fixture openings awaiting placement",
            "Saved sizes retained after a fixture-type change; previous locations are not cut",
            len(pending),
            "not_evaluated",
            units="openings",
            correction="Select each pending opening and click its location on the new fixture, then rebuild.",
        )
    expected = opening_tools(r, plan)
    actual = tuple(o for o in plan.operations if o.id.startswith(PREFIX))
    if not actual and not expected:
        return
    matches = [o.model_dump(exclude={"depends_on"}) for o in actual] == [
        o.model_dump(exclude={"depends_on"}) for o in expected
    ]
    add(
        "Fixture opening schedule",
        "Regenerated user positions, targets, diameters and full fixture depths",
        len(actual),
        "passed" if matches else "failed",
        units="openings",
    )
    for tool in expected:
        residual = sum(
            abs(sm.booleans.boolean_intersection(body.copy(), primitive(tool)).volume())
            for body in bodies.values()
        )
        add(
            "Fixture through opening: " + tool.id.removeprefix(PREFIX),
            "Independent full-depth cylinder intersection against every final fixture body",
            residual,
            "passed" if residual < MM_TOL else "failed",
            units="mm³",
            correction="Another fixture part blocks the opening. Move the hole to a clear area.",
        )
