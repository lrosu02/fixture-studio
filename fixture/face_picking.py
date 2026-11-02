"""Select measured planar mounting interfaces; browser events carry IDs only."""

from uuid import uuid4
import numpy as np
import plotly.graph_objects as go
from pydantic import Field
from .contracts import Mesh, Record, MM_TOL
from .intake import get_interface, local_points
from .planning import patch_requirements
from .viewer import add_mesh


class FacePicks(Record):
    context: str = Field(default_factory=lambda: uuid4().hex)
    interface_id: str | None = None


class FaceSelection(Record):
    context: str
    interface_id: str


def pick_face(analysis, picks, event):
    selected = FaceSelection.model_validate(event)
    if selected.context != picks.context:
        raise ValueError(
            "This face click belongs to an older selection. Click the face again."
        )
    get_interface(analysis, selected.interface_id)
    return picks.model_copy(update={"interface_id": selected.interface_id})


def use_picked_face(analysis, requirements, picks, hole_ids, confirmed):
    if not confirmed:
        raise ValueError(
            "Confirm the mounting surface and selected fastener holes before applying."
        )
    interface = get_interface(analysis, picks.interface_id)
    if len(set(hole_ids)) != len(hole_ids) or not set(hole_ids) <= set(
        interface.hole_ids
    ):
        raise ValueError("Choose the detected fastener holes on this mounting face.")
    changes = dict(
        interface_id=interface.id,
        mounting_hole_ids=tuple(hole_ids),
        mounting_confirmed=True,
        part_attachment="screws"
        if hole_ids
        else requirements.part_attachment
        if requirements.part_attachment
        in ("cradle", "strap", "nest", "saddle", "collar", "split_clamp")
        else "unselected",
    )
    if interface.id != requirements.interface_id:
        # These boxes are defined in the old attachment frame, not world space.
        changes["envelopes"] = ()
    return patch_requirements(requirements, changes)


def face_surface(analysis, interface):
    if interface.face_mesh is not None:
        return interface.face_mesh
    # Legacy snapshots predate per-face meshes. Show existing triangles on the
    # measured plane within its trim bounds; never fabricate a filled polygon.
    # This is display-only, and does not create/update CAD face evidence.
    vertices = np.asarray(analysis.mesh.vertices)
    triangles = np.asarray(analysis.mesh.triangles)
    local = local_points(vertices, interface)
    trim = local_points(interface.boundary, interface)
    inside = (
        (abs(local[:, 2]) < MM_TOL)
        & np.all(local[:, :2] >= trim[:, :2].min(axis=0) - MM_TOL, axis=1)
        & np.all(local[:, :2] <= trim[:, :2].max(axis=0) + MM_TOL, axis=1)
    )
    facets = vertices[triangles]
    normals = np.cross(facets[:, 1] - facets[:, 0], facets[:, 2] - facets[:, 0])
    chosen = triangles[
        inside[triangles].all(axis=1) & (normals @ np.asarray(interface.z) < 0)
    ]
    used, remap = np.unique(chosen, return_inverse=True)
    return Mesh(
        vertices=tuple(map(tuple, vertices[used])),
        triangles=tuple(map(tuple, remap.reshape(-1, 3))),
    )


def face_label(interface):
    if interface.support_kind == "cylinder":
        return f"Cylindrical face {interface.face_ref + 1} · Ø{2 * interface.support_radius:g} mm"
    if not interface.hole_ids:
        return f"Face {interface.face_ref + 1} · no circular holes"
    sizes = ", ".join(
        f"{d:g}" for d in sorted({round(d, 3) for d in interface.diameters})
    )
    return (
        f"Face {interface.face_ref + 1} · {len(interface.hole_ids)} holes · Ø{sizes} mm"
    )


def face_picker_figure(analysis):
    fig = go.Figure()
    add_mesh(fig, analysis.mesh, "#697581", "Uploaded STEP", hoverinfo="skip")
    extent = max(np.ptp(np.asarray(analysis.mesh.vertices), axis=0))
    for interface in analysis.interfaces:
        surface = face_surface(analysis, interface)
        if surface.triangles:
            p = np.asarray(surface.vertices) - np.asarray(interface.z) * 0.04
            t = np.asarray(surface.triangles)
            fig.add_trace(
                go.Mesh3d(
                    x=p[:, 0],
                    y=p[:, 1],
                    z=p[:, 2],
                    i=t[:, 0],
                    j=t[:, 1],
                    k=t[:, 2],
                    color="#74a9bc",
                    flatshading=True,
                    opacity=1,
                    showlegend=False,
                    meta={"interface_id": interface.id, "pick_kind": "face"},
                    name=face_label(interface),
                    text=face_label(interface)
                    + "<br>Click to select this mounting surface",
                    hoverinfo="skip",
                    lighting=dict(ambient=0.7, diffuse=0.6, specular=0.1),
                )
            )
        # Arrow points outward from the source: the side occupied by the fixture.
        origin = np.asarray(interface.origin)
        if surface.triangles:
            facets = np.asarray(surface.vertices)[np.asarray(surface.triangles)]
            areas = np.linalg.norm(
                np.cross(facets[:, 1] - facets[:, 0], facets[:, 2] - facets[:, 0]),
                axis=1,
            )
            # A flange's plane origin can lie inside its protruding body. Start
            # the arrow on actual surface material, where its direction is visible.
            origin = facets[int(np.argmax(areas))].mean(axis=0)
        tip = origin - np.asarray(interface.z) * extent * 0.2
        direction = np.asarray([origin, tip])
        fig.add_trace(
            go.Scatter3d(
                x=direction[:, 0],
                y=direction[:, 1],
                z=direction[:, 2],
                mode="lines",
                line=dict(color="#ffb454", width=7),
                meta={"direction_for": interface.id},
                visible=False,
                showlegend=False,
                text="Fixture side of selected face",
                hoverinfo="text",
            )
        )
        fig.add_trace(
            go.Cone(
                x=[tip[0]],
                y=[tip[1]],
                z=[tip[2]],
                u=[-interface.z[0]],
                v=[-interface.z[1]],
                w=[-interface.z[2]],
                sizemode="absolute",
                sizeref=extent * 0.06,
                anchor="tip",
                showscale=False,
                colorscale=[[0, "#ffb454"], [1, "#ffb454"]],
                meta={"direction_for": interface.id},
                visible=False,
                hoverinfo="skip",
            )
        )
    fig.update_layout(
        height=510,
        margin=dict(l=0, r=0, b=0, t=5),
        paper_bgcolor="#101820",
        font_color="#dce5ed",
        scene=dict(
            aspectmode="data",
            xaxis_title="X · mm",
            yaxis_title="Y · mm",
            zaxis_title="Z · mm",
        ),
        showlegend=False,
        uirevision=analysis.source_hash,
    )
    return fig
