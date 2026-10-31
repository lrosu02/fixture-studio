"""Translate generated SMLib BRep topology to STEP; never replay modeling operations.

The supported fixture vocabulary emits planes/cylinders/cones with rational NURBS edges.
The topology convention follows NVIDIA's documented BrepArray converter:
https://github.com/NVIDIA-Omniverse/usd-brep/tree/main/source/OCCT_BREP_EXPORT
No tessellated faces, sampled replacement curves, or second USD runtime are used.
"""

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import tempfile
import threading

import numpy as np

ADAPTER_VERSION = 2
_LOCK = threading.RLock()


def _array(cls, values):
    result = cls(1, len(values))
    for n, value in enumerate(values, 1):
        result.SetValue(n, value)
    return result


def _body(block):
    import cadquery as cq
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax3
    from OCP.Geom import (
        Geom_BSplineCurve,
        Geom_Plane,
        Geom_CylindricalSurface,
        Geom_ConicalSurface,
    )
    from OCP.TColgp import TColgp_Array1OfPnt
    from OCP.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex, BRepBuilderAPI_MakeEdge
    from OCP.TopoDS import TopoDS_Face, TopoDS_Wire, TopoDS_Shell, TopoDS_Solid
    from OCP.ShapeFix import ShapeFix_Edge, ShapeFix_Shape

    # This is deliberately a reader for the pinned exporter output, not a USD
    # scene loader. Literal parsing accepts numeric/string arrays without code.
    data = {
        key: ast.literal_eval(value)
        for key, value in re.findall(
            r"^\s*uniform \w+\[\] ([\w:]+) = (.+)$", block, re.M
        )
    }
    if (
        len(data.get("face:surfaceType", ())) > 4096
        or len(data.get("edge:curveType", ())) > 16384
    ):
        raise ValueError("STEP conversion exceeds the bounded topology limit.")
    if set(data["edge:curveType"]) != {"BrepCurve3dNurbAPI"}:
        raise ValueError(
            "STEP adapter needs the generated rational NURBS edge representation."
        )
    if not set(data["face:surfaceType"]) <= {
        "BrepSurfacePlaneAPI",
        "BrepSurfaceCylinderAPI",
        "BrepSurfaceConeAPI",
    }:
        raise ValueError(
            "STEP export supports generated planar/cylindrical fixtures; this surface type needs an adapter extension."
        )
    if not 1 <= data["region:type"].count("solidRegion") <= 64 or any(
        data.get("shell:wireEdgeCount", [])
    ):
        raise ValueError(
            "STEP export requires bounded closed solids without wire shells."
        )
    builder = BRep_Builder()
    tolerance = 2e-5
    vertices = []
    for point in data["brep:vertexPoint:point:position"]:
        vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
        builder.UpdateVertex(vertex, tolerance)
        vertices.append(vertex)
    prefix = "brep:edge3dNurb:curve3d:nurb:"
    edges, pole_start, knot_start = [], 0, 0
    counts, orders = data[prefix + "vertexCount"], data[prefix + "order"]
    if len(counts) != len(data["edge:curveType"]) or len(counts) != len(orders):
        raise ValueError("Inconsistent STEP edge tables.")
    for index, (count, order) in enumerate(zip(counts, orders)):
        poles = [
            gp_Pnt(*p)
            for p in data[prefix + "controlVertices"][pole_start : pole_start + count]
        ]
        weights = data[prefix + "weights"][pole_start : pole_start + count]
        flat = data[prefix + "knots"][knot_start : knot_start + count + order]
        if (
            len(poles) != count
            or len(weights) != count
            or len(flat) != count + order
            or flat != sorted(flat)
        ):
            raise ValueError("Incomplete or unordered NURBS data.")
        knots = Counter(flat)
        curve = Geom_BSplineCurve(
            _array(TColgp_Array1OfPnt, poles),
            _array(TColStd_Array1OfReal, weights),
            _array(TColStd_Array1OfReal, list(knots)),
            _array(TColStd_Array1OfInteger, list(knots.values())),
            order - 1,
            False,
        )
        v1, v2 = data["edge:vertexIndices"][index]
        lo, hi = data["edge:range"][index * 2 : index * 2 + 2]
        if min(v1, v2) < 0 or max(v1, v2) >= len(vertices) or hi <= lo:
            raise ValueError("Unsupported or invalid edge topology.")
        maker = BRepBuilderAPI_MakeEdge(curve, vertices[v1], vertices[v2], lo, hi)
        if not maker.IsDone():
            raise ValueError(
                f"STEP edge {index} could not be transferred: {maker.Error()}"
            )
        edges.append(maker.Edge())
        pole_start += count
        knot_start += count + order
    faces, loop_index, edgeuse_index, surface_index = [], 0, 0, Counter()
    for kind, loop_count in zip(data["face:surfaceType"], data["face:loopCount"]):
        kind = {
            "BrepSurfacePlaneAPI": "plane",
            "BrepSurfaceCylinderAPI": "cylinder",
            "BrepSurfaceConeAPI": "cone",
        }[kind]
        index = surface_index[kind]
        surface_index[kind] += 1
        key = "brep:surface:" + kind + ":"
        axes = gp_Ax3(
            gp_Pnt(*data[key + "origin"][index]),
            gp_Dir(*data[key + "axis"][index]),
            gp_Dir(*data[key + "refDirection"][index]),
        )
        surface = (
            Geom_Plane(axes)
            if kind == "plane"
            else (
                Geom_CylindricalSurface(axes, data[key + "radius"][index])
                if kind == "cylinder"
                else Geom_ConicalSurface(
                    axes, data[key + "semiAngle"][index], data[key + "radius"][index]
                )
            )
        )
        face = TopoDS_Face()
        builder.MakeFace(face, surface, tolerance)
        uses = []
        for _ in range(loop_count):
            wire = TopoDS_Wire()
            builder.MakeWire(wire)
            for _ in range(data["loop:edgeuseCount"][loop_index]):
                edge_index = data["edgeuse:edgeIndex"][edgeuse_index]
                orientation = data["edgeuse:orientationType"][edgeuse_index]
                if orientation not in ("same", "opposite"):
                    raise ValueError("Unsupported edge orientation.")
                builder.Add(
                    wire,
                    edges[edge_index].Reversed()
                    if orientation == "opposite"
                    else edges[edge_index],
                )
                uses.append(edge_index)
                edgeuse_index += 1
            wire.Closed(True)
            builder.Add(face, wire)
            loop_index += 1
        # Reconstruct surface parameter curves from the preserved 3D curves.
        # Seams receive paired pcurves, without altering the 3D geometry.
        for edge_index, count in Counter(uses).items():
            ShapeFix_Edge().FixAddPCurve(edges[edge_index], face, count > 1, tolerance)
        faces.append(face)
    if edgeuse_index != len(data["edgeuse:edgeIndex"]) or loop_index != len(
        data["loop:edgeuseCount"]
    ):
        raise ValueError("STEP topology contains unconsumed loops or edge uses.")
    shell_index, faceuse_index, solids = 0, 0, []
    for kind, shell_count in zip(data["region:type"], data["region:shellCount"]):
        solid = TopoDS_Solid()
        builder.MakeSolid(solid)
        region_faces = set()
        for index in range(shell_count):
            shell = TopoDS_Shell()
            builder.MakeShell(shell)
            for _ in range(data["shell:faceuseCount"][shell_index]):
                face_index = data["faceuse:faceIndex"][faceuse_index]
                region_faces.add(face_index)
                face = faces[face_index]
                orientation = data["faceuse:orientationType"][faceuse_index]
                if orientation not in ("same", "opposite"):
                    raise ValueError("Unsupported face orientation.")
                # A solid-region opposite faceuse is forward in an OCCT shell.
                builder.Add(shell, face.Reversed() if orientation == "same" else face)
                faceuse_index += 1
            shell_index += 1
            shell.Closed(True)
            builder.Add(solid, shell if index == 0 else shell.Reversed())
        if kind == "solidRegion":
            fix = ShapeFix_Shape(solid)
            fix.SetPrecision(tolerance)
            fix.SetMaxTolerance(0.001)
            fix.Perform()
            shape = cq.Shape.cast(fix.Shape())
            if (
                not shape.isValid()
                or len(shape.Solids()) != 1
                or len(shape.Faces()) != len(region_faces)
            ):
                raise ValueError(
                    "Transferred STEP body lost validity, faces or solid topology."
                )
            solids.append(shape)
    if shell_index != len(data["shell:faceuseCount"]) or faceuse_index != len(
        data["faceuse:faceIndex"]
    ):
        raise ValueError("STEP topology contains unconsumed shells or face uses.")
    return solids


def _properties(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    volume, area = GProp_GProps(), GProp_GProps()
    # Adaptive integration matters for rational circular trims; default fixed
    # quadrature can differ by several mm3 on otherwise identical CAD.
    BRepGProp.VolumeProperties_s(shape.wrapped, volume, 1e-9, True, False)
    BRepGProp.SurfaceProperties_s(shape.wrapped, area, 1e-9, False)
    box = shape.BoundingBox()
    return (
        volume.Mass(),
        area.Mass(),
        ((box.xmin, box.ymin, box.zmin), (box.xmax, box.ymax, box.zmax)),
    )


def _check(shapes, native):
    from OCP.BRepCheck import BRepCheck_Analyzer

    if len(shapes) != len(native):
        raise ValueError("STEP solid count differs from native CAD.")
    records = []
    # STEP writer preserves solid order for the generated flat compound.
    for shape, original in zip(shapes, native):
        volume, area, bounds = _properties(shape)
        nv, na = original.volume(1e-7), original.area(1e-7)
        if (
            not BRepCheck_Analyzer(shape.wrapped).IsValid()
            or volume <= 0
            or len(shape.Faces()) != original.face_count()
            or abs(volume - nv) > max(0.01, abs(nv) * 1e-5)
            or abs(area - na) > max(0.01, abs(na) * 1e-5)
            or not np.allclose(bounds, original.bounding_box(), atol=0.01, rtol=0)
        ):
            raise ValueError(
                "STEP verification failed validity, face count, volume, area or bounds comparison."
            )
        records.append(
            {
                "volume_mm3": volume,
                "native_volume_mm3": nv,
                "area_mm2": area,
                "native_area_mm2": na,
                "faces": len(shape.Faces()),
                "bounds_mm": bounds,
            }
        )
    return records


def prepared_step(revision):
    """Only offer a previously verified STEP if both geometry hashes still match."""
    source = Path(revision.artifact)
    target = source.with_suffix(".step")
    try:
        report = json.loads(
            source.with_name("step-export.json").read_text(encoding="utf-8")
        )
        if (
            report.get("adapter_version") == ADAPTER_VERSION
            and report.get("revision_id") == revision.id
            and report.get("result") == "passed"
            and report.get("source_sha256")
            == hashlib.sha256(source.read_bytes()).hexdigest()
            and report.get("step_sha256")
            == hashlib.sha256(target.read_bytes()).hexdigest()
        ):
            return target
    except (OSError, ValueError):
        pass
    return None


def prepare_step(revision):
    """Convert a selected immutable revision once, including historical revisions."""
    import cadquery as cq
    import usd_brep as sm
    from .executor import KERNEL_LOCK

    source = Path(revision.artifact)
    target, report_path = (
        source.with_suffix(".step"),
        source.with_name("step-export.json"),
    )
    with _LOCK, KERNEL_LOCK:
        if source.stat().st_size > 50_000_000:
            raise ValueError(
                "Native CAD file exceeds the bounded STEP conversion size."
            )
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if prepared_step(revision):
            return target
        text = payload.decode("utf-8")
        if not re.search(r"metersPerUnit\s*=\s*0\.001\b", text):
            raise ValueError("STEP conversion requires a generated millimeter stage.")
        if "xformOp:" in text or "@" in text:
            raise ValueError(
                "STEP conversion accepts generated fixture BReps without external references or scene transforms."
            )
        blocks = re.split(r'\bdef BrepArray "[^"\n]+"', text)[1:]
        if not 1 <= len(blocks) <= 64:
            raise ValueError(
                "No supported generated BRep bodies found for STEP export."
            )
        native = sm.usd.import_breps(str(source))
        shapes = [solid for block in blocks for solid in _body(block)]
        _check(shapes, native)
        with tempfile.TemporaryDirectory(
            prefix=".step-save-", dir=source.parent, ignore_cleanup_errors=True
        ) as folder:
            candidate = Path(folder) / "fixture.step"
            cq.exporters.export(
                cq.Compound.makeCompound(shapes), str(candidate), exportType="STEP"
            )
            reopened = cq.importers.importStep(str(candidate)).val()
            records = _check(reopened.Solids(), native)
            report = {
                "adapter_version": ADAPTER_VERSION,
                "revision_id": revision.id,
                "source_sha256": digest,
                "step_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                "units": "mm",
                "contents": "Generated fixture solids only; source part excluded",
                "method": "SMLib BRep surfaces/curves/topology transferred to OCCT; STEP reopened and verified; no mesh conversion",
                "result": "passed",
                "bodies": records,
            }
            candidate.replace(target)
            temporary_report = Path(folder) / "step-export.json"
            temporary_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
            temporary_report.replace(report_path)
        return target
