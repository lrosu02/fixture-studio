"""OCCT owns source parsing and measurement only. No fixture construction here."""

from functools import lru_cache
from pathlib import Path
import hashlib
import math
import tempfile
import numpy as np
import cadquery as cq
from OCP.STEPControl import STEPControl_Reader
from OCP.TColStd import TColStd_SequenceOfAsciiString
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.TopAbs import TopAbs_IN, TopAbs_ON
from OCP.gp import gp_Pnt
from .contracts import Analysis, Feature, Interface, Mesh, MM_TOL


def local_points(points, interface):
    basis = np.array([interface.x, interface.y, interface.z])
    return (np.asarray(points) - np.array(interface.origin)) @ basis.T


def get_interface(analysis, interface_id):
    for item in analysis.interfaces:
        if item.id == interface_id:
            return item
    raise ValueError("Select a measured mounting interface first.")


def selected_interface(analysis, requirements):
    i = get_interface(analysis, requirements.interface_id)
    if requirements.part_attachment != "screws":
        return i.model_copy(
            update={
                **{
                    k: ()
                    for k in (
                        "hole_ids",
                        "centers",
                        "diameters",
                        "contact_radii",
                        "contact_valid",
                    )
                },
                "contact_ok": True,
            }
        )
    if not requirements.mounting_hole_ids:
        return i
    if not set(requirements.mounting_hole_ids) <= set(i.hole_ids):
        raise ValueError("Selected mounting features do not belong to this interface.")
    indices = [
        n for n, h in enumerate(i.hole_ids) if h in requirements.mounting_hole_ids
    ]
    return i.model_copy(
        update={
            **{
                field: tuple(getattr(i, field)[n] for n in indices)
                for field in (
                    "hole_ids",
                    "centers",
                    "diameters",
                    "contact_radii",
                    "contact_valid",
                )
            },
            "contact_ok": all(i.contact_valid[n] for n in indices),
        }
    )


def recommended_interface(analysis):
    eligible = []
    for i in analysis.interfaces:
        pts = local_points(analysis.mesh.vertices, i)
        if pts[:, 2].min() >= -MM_TOL and i.contact_ok:
            eligible.append(i)
    # Never infer stationary meaning from geometry. This only selects geometry.
    drilled = [i for i in eligible if i.hole_ids]
    return drilled[0].id if len(drilled) == 1 else None


def _wire_points(wire):
    points = []
    for e in wire.Edges():
        points.extend(e.positionAt(t).toTuple() for t in np.linspace(0, 1, 25))
    return tuple(points)


@lru_cache(maxsize=12)
def analyze_bytes(data: bytes, name: str, selected: tuple[int, ...] | None = None):
    if len(data) > 30_000_000:
        raise ValueError("STEP exceeds 30 MB local prototype limit.")
    if b"ISO-10303-21" not in data[:4096]:
        raise ValueError("Expected an ISO-10303-21 STEP file.")
    cache = Path(__file__).resolve().parents[1] / "artifacts" / "intake"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temp:
        path = Path(temp) / "source.step"
        path.write_bytes(data)
        reader = STEPControl_Reader()
        reader.ReadFile(str(path))
        lengths, angles, solids_units = (
            TColStd_SequenceOfAsciiString() for _ in range(3)
        )
        reader.FileUnits(lengths, angles, solids_units)
        units = tuple(
            lengths.Value(i).ToCString() for i in range(1, lengths.Length() + 1)
        )
        shape = cq.importers.importStep(str(path), unit="MM").val()
    solids = shape.Solids()
    if not solids:
        raise ValueError("No solid bodies found. Surface-only STEP is unsupported.")
    ids = tuple(range(len(solids))) if selected is None else selected
    if selected is None and len(ids) > 16:
        raise ValueError(
            "This STEP exceeds the current limit of 16 solids per imported part. Export a smaller component as STEP; no pieces were discarded."
        )
    if (
        not ids
        or len(ids) > 16
        or len(set(ids)) != len(ids)
        or any(i < 0 or i >= len(solids) for i in ids)
    ):
        raise ValueError("Choose between one and sixteen valid body IDs.")
    part = cq.Compound.makeCompound([solids[i] for i in ids])
    if not part.isValid():
        raise ValueError(
            "OCCT reports invalid source topology; repair the STEP before upload."
        )
    vertices, triangles = part.tessellate(0.15)
    mesh = Mesh(
        vertices=tuple(v.toTuple() for v in vertices), triangles=tuple(triangles)
    )
    bb = part.BoundingBox()
    features, interfaces = [], []
    cylinders = []
    for index, candidate in enumerate(part.Faces()):
        if candidate.geomType() == "CYLINDER":
            cyl = candidate._geomAdaptor().Cylinder()
            axis = np.array(cyl.Axis().Direction().Coord())
            center = np.array(cyl.Location().Coord())
            point = np.array(candidate.positionAt(0.5, 0.5).toTuple())
            radial = point - center - axis * np.dot(point - center, axis)
            normal = np.array(candidate.normalAt(cq.Vector(*point)).toTuple())
            if np.dot(radial, normal) < 0:
                cylinders.append((index, center, axis, cyl.Radius()))
    for fi, face in enumerate(part.Faces()):
        if face.geomType() != "PLANE":
            continue
        z = -np.array(face.normalAt().toTuple())
        measured = []
        # Circular inner boundaries are topological holes, unlike outer bosses.
        for wire in face.innerWires():
            wire_edges = wire.Edges()
            if any(e.geomType() != "CIRCLE" for e in wire_edges):
                continue  # Slots and mixed boundaries are not circular holes.
            circles = [e._geomAdaptor().Circle() for e in wire_edges]
            if any(
                np.linalg.norm(
                    np.array(c.Location().Coord())
                    - np.array(circles[0].Location().Coord())
                )
                > MM_TOL
                for c in circles
            ):
                continue
            if (
                abs(
                    sum(e.Length() for e in wire_edges)
                    - 2 * math.pi * circles[0].Radius()
                )
                > MM_TOL
            ):
                continue
            for e in wire.Edges():
                if e.geomType() != "CIRCLE":
                    continue
                circle = e._geomAdaptor().Circle()
                center = np.array(circle.Location().Coord())
                axis = np.array(circle.Axis().Direction().Coord())
                if abs(np.dot(axis, z)) < 0.999:
                    continue
                radius = circle.Radius()
                # Coaxial split arcs at this plane collapse into one feature.
                if any(np.linalg.norm(center - c) < MM_TOL for c, r in measured):
                    continue
                measured.append((center, radius))
        origin = (
            np.mean([c for c, r in measured], axis=0)
            if measured
            else np.array(face.Center().toTuple())
        )
        edges = [e for e in face.outerWire().Edges() if e.geomType() == "LINE"]
        if edges:
            edge = max(edges, key=lambda e: round(e.Length(), 5))
            x = np.array(edge.tangentAt().toTuple())
        else:
            x = measured[0][0] - origin if measured else np.zeros(3)
            if np.linalg.norm(x) < MM_TOL:
                seed = np.eye(3)[np.argmin(abs(z))]
                x = np.cross(seed, z)
        x = x - z * np.dot(x, z)
        x /= np.linalg.norm(x)
        y = np.cross(z, x)
        basis = np.array([x, y, z])
        hole_ids, centers, diameters, radii, contact_valid = [], [], [], [], []
        contact_ok = True
        for hi, (center, radius) in enumerate(measured):
            hole_contact = True
            hid = f"f{fi}-h{hi}"
            hole_ids.append(hid)
            centers.append(tuple(basis @ (center - origin)))
            coaxial = [
                (index, rr)
                for index, cc, axis, rr in cylinders
                if abs(np.dot(axis, z)) > 0.999
                and np.linalg.norm((center - cc) - axis * np.dot(center - cc, axis))
                < MM_TOL
            ]
            bore_radius = min([radius] + [rr for _, rr in coaxial])
            diameters.append(bore_radius * 2)
            # A sampled annular contact patch, explicitly not full containment.
            outer = radius + max(1.5, radius * 0.6)
            radii.append(outer)
            for r in (radius + 0.25, (radius + outer) / 2, outer):
                for theta in np.linspace(0, 2 * math.pi, 32, endpoint=False):
                    p = center + r * (math.cos(theta) * x + math.sin(theta) * y)
                    state = BRepClass_FaceClassifier(
                        face.wrapped, gp_Pnt(*p), MM_TOL
                    ).State()
                    hole_contact &= state in (TopAbs_IN, TopAbs_ON)
            contact_valid.append(bool(hole_contact))
            contact_ok &= hole_contact
            features.append(
                Feature(
                    id=hid,
                    face_refs=(fi,) + tuple(index for index, _ in coaxial),
                    kind="hole",
                    position=tuple(center),
                    axis=tuple(z),
                    diameter=bore_radius * 2,
                    evidence="Closed circular inner boundary; coaxial inward cylindrical faces grouped, smallest modeled bore retained. Modeled diameter is not a thread size.",
                )
            )
        features.append(
            Feature(
                id=f"f{fi}",
                face_refs=(fi,),
                kind="plane",
                position=tuple(origin),
                axis=tuple(z),
                evidence="Analytic planar face with retained outer and inner trim boundaries.",
            )
        )
        transform = np.eye(4)
        transform[:3, :3] = basis
        transform[:3, 3] = -basis @ origin
        face_vertices, face_triangles = face.tessellate(0.15)
        interfaces.append(
            Interface(
                id=f"interface-{fi}",
                face_ref=fi,
                origin=tuple(origin),
                x=tuple(x),
                y=tuple(y),
                z=tuple(z),
                hole_ids=tuple(hole_ids),
                centers=tuple(centers),
                diameters=tuple(diameters),
                boundary=_wire_points(face.outerWire()),
                exclusions=tuple(_wire_points(w) for w in face.innerWires()),
                contact_radii=tuple(radii),
                contact_valid=tuple(contact_valid),
                contact_ok=bool(contact_ok),
                confidence=(
                    f"{len(measured)} circular inner boundaries; contact annuli sampled at 96 points per hole. Stationary meaning requires confirmation."
                    if measured
                    else "Measured planar surface with no circular holes. Confirm the contact side and choose how the part should be retained."
                ),
                source_to_local=tuple(tuple(row) for row in transform),
                face_mesh=Mesh(
                    vertices=tuple(v.toTuple() for v in face_vertices),
                    triangles=tuple(face_triangles),
                ),
                area_mm2=face.Area(),
            )
        )
    # Analytic outside cylinders get a measured tangent support frame. This is
    # explicitly cylindrical contact, never fabricated planar-face evidence.
    for fi,face in enumerate(part.Faces()):
        if face.geomType()!='CYLINDER':
            continue
        surf=face._geomAdaptor(); cyl=surf.Cylinder()
        u0,u1,_,_=face._uvBounds()
        if abs(u1-u0-2*math.pi)>1e-5:
            continue
        axis=np.array(cyl.Axis().Direction().Coord()); center=np.array(cyl.Location().Coord())
        point=np.array(face.positionAt(.5,.5).toTuple())
        radial=point-center-axis*np.dot(point-center,axis)
        if np.dot(radial,np.array(face.normalAt(cq.Vector(*point)).toTuple()))<=0:
            continue
        vs,ts=face.tessellate(.15); points=np.array([v.toTuple() for v in vs])
        along=(points-center)@axis
        z=np.array(cyl.XAxis().Direction().Coord());y=axis;x=np.cross(y,z)
        origin=center+axis*(along.min()+along.max())/2-z*cyl.Radius()
        basis=np.array([x,y,z]);transform=np.eye(4);transform[:3,:3]=basis;transform[:3,3]=-basis@origin
        interfaces.append(Interface(id=f'cylinder-interface-{fi}',face_ref=fi,origin=tuple(origin),x=tuple(x),y=tuple(y),z=tuple(z),hole_ids=(),centers=(),diameters=(),boundary=_wire_points(face.outerWire()),exclusions=(),contact_radii=(),contact_valid=(),contact_ok=True,confidence='Measured complete outer cylinder; tangent frame for a saddle, collar or split clamp. Confirm the supported surface and access.',source_to_local=tuple(map(tuple,transform)),face_mesh=Mesh(vertices=tuple(map(tuple,points)),triangles=tuple(ts)),area_mm2=face.Area(),support_kind='cylinder',support_radius=cyl.Radius(),support_length=float(along.max()-along.min())))
    return Analysis(
        source_name=Path(name).name,
        source_hash=hashlib.sha256(data).hexdigest(),
        original_units=units,
        normalization="OCCT STEP reader converts declared units to millimeters; imported placements retained.",
        selected_bodies=ids,
        body_count=len(solids),
        bounds=((bb.xmin, bb.ymin, bb.zmin), (bb.xmax, bb.ymax, bb.zmax)),
        mesh=mesh,
        features=tuple(features),
        interfaces=tuple(sorted(interfaces, key=lambda i: not bool(i.hole_ids))),
        limitations=(
            "Contact is sampled, not a proof of full trimmed-footprint containment.",
            "Chamfer opening diameter may differ from bore diameter; confirm clearance and interface.",
            "No thread recognition, automatic repair or exact source/fixture collision bridge.",
            "Inner circular boundaries may be ports; confirm which features are fastener holes.",
        ),
    )


def analyze_file(path, selected=None):
    path = Path(path)
    return analyze_bytes(path.read_bytes(), path.name, selected)
