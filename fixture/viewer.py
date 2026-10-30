import numpy as np
import plotly.graph_objects as go
from .intake import get_interface, local_points
from .render_mesh import display_indices


def hole_size_key(diameter):
    """Display precision only; never round source measurements or CAD inputs."""
    return f"{diameter:.3f}"


def hole_size_colors(analysis):
    """Stable across picks/faces in an immutable analysis, ordered by bore size."""
    sizes = sorted(
        {hole_size_key(d) for i in analysis.interfaces for d in i.diameters},
        key=float,
    )
    palette = (
        "#56b4e9",
        "#e69f00",
        "#cc79a7",
        "#00c99b",
        "#f07060",
        "#f0e442",
        "#b7a1ff",
        "#f6b9d2",
    )
    return {
        size: palette[n]
        if n < len(palette)
        else f"hsl({(n * 137.508) % 360:.3f},75%,65%)"
        for n, size in enumerate(sizes)
    }


def add_mesh(fig, mesh, color, name, points=None, opacity=1, hoverinfo=None):
    p = np.asarray(mesh.vertices if points is None else points)
    indices, t = display_indices(mesh)
    p = p[indices]
    fig.add_trace(
        go.Mesh3d(
            x=p[:, 0],
            y=p[:, 1],
            z=p[:, 2],
            i=t[:, 0],
            j=t[:, 1],
            k=t[:, 2],
            color=color,
            name=name,
            opacity=opacity,
            hoverinfo=hoverinfo,
            showlegend=True,
            flatshading=False,
            lighting=dict(ambient=0.6, diffuse=0.7, specular=0.15, roughness=0.7),
        )
    )


def assembly_figure(
    analysis,
    interface_id=None,
    revision=None,
    source=True,
    fixture=True,
    evidence=True,
    dimensions=False,
    envelopes=False,
    previous=None,
    highlight_ids=(),
):
    fig = go.Figure()
    interface = (
        get_interface(
            analysis, revision.plan.interface_id if revision else interface_id
        )
        if (revision or interface_id)
        else None
    )
    placements = revision.plan.placements if revision else ((0, 0, 0),)
    points = (
        local_points(analysis.mesh.vertices, interface)
        if interface
        else np.asarray(analysis.mesh.vertices)
    )
    if source:
        for n, p in enumerate(placements):
            add_mesh(
                fig, analysis.mesh, "#9ba9b9", f"Source {n + 1}", points + np.array(p)
            )
    if revision and fixture:
        for name, mesh in revision.meshes.items():
            add_mesh(fig, mesh, "#25afa3", name)
    if source and revision and revision.requirements.base_mount:
        from .existing_base import transform
        r=revision.requirements
        base=r.base_mount
        frame=get_interface(base.analysis,base.interface_id)
        origin,basis=transform(r,revision.plan)
        points=local_points(base.analysis.mesh.vertices,frame)@basis+origin
        add_mesh(fig,base.analysis.mesh,'#7586bc','Existing base',points)
    if previous:
        for name, mesh in previous.meshes.items():
            add_mesh(fig, mesh, "#f6a94b", "Previous " + name, opacity=0.18)
    if evidence and interface:
        colors = hole_size_colors(analysis)
        shown_sizes = set()
        for p in placements:
            for hid, c, d in zip(
                interface.hole_ids, interface.centers, interface.diameters
            ):
                if (
                    highlight_ids
                    and interface.id not in highlight_ids
                    and hid not in highlight_ids
                ):
                    continue
                theta = np.linspace(0, 2 * np.pi, 49)
                c = np.array(c) + p
                size = hole_size_key(d)
                fig.add_trace(
                    go.Scatter3d(
                        x=c[0] + d / 2 * np.cos(theta),
                        y=c[1] + d / 2 * np.sin(theta),
                        z=np.full(49, c[2] + 0.08),
                        mode="lines",
                        line=dict(color=colors[size], width=6),
                        name=f"Ø {size} mm measured",
                        legendgroup="bore-" + size,
                        showlegend=size not in shown_sizes,
                        text=f"{hid}: modeled diameter {d:.3f} mm",
                        hoverinfo="text",
                    )
                )
                shown_sizes.add(size)
    if dimensions and revision:
        fig.add_annotation(
            text=" | ".join(f"{k}: {v}" for k, v in revision.plan.parameters.items()),
            x=0.5,
            y=0,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
    if revision and (
        envelopes or any(h.startswith("rear-profile-") for h in highlight_ids)
    ):
        show_rear_legend = True
        for op in revision.plan.operations:
            if not op.id.startswith("rear-relief-"):
                continue
            if (
                not envelopes
                and "rear-profile-" + op.id.rsplit("-", 1)[-1] not in highlight_ids
            ):
                continue
            if op.shape == "cylinder":
                theta = np.linspace(0, 2 * np.pi, 65)[:-1]
                outline = (
                    np.column_stack((np.cos(theta), np.sin(theta))) * op.size[0] / 2
                )
            elif op.shape == "prism":
                outline = np.array(op.profile)
            else:
                x, y = op.size[:2]
                outline = np.array([(0, 0), (x, 0), (x, y), (0, y)])
            bottom = np.column_stack((outline, np.zeros(len(outline)))) + op.origin
            vertices = np.concatenate((bottom, bottom + [0, 0, op.size[2]]))
            if not envelopes:
                # A selected recess is an outline, not a translucent cap that
                # could make a through opening look closed in the normal view.
                rim = np.vstack((bottom, bottom[0]))
                fig.add_trace(
                    go.Scatter3d(
                        x=rim[:, 0],
                        y=rim[:, 1],
                        z=np.full(len(rim), 0.08),
                        mode="lines",
                        line=dict(color="#c4a5ff", width=4),
                        name="Measured rear clearance",
                        legendgroup="rear-clearance",
                        showlegend=show_rear_legend,
                        hovertemplate=op.id + "<extra>Selected passage outline</extra>",
                    )
                )
                show_rear_legend = False
                continue
            fig.add_trace(
                go.Mesh3d(
                    x=vertices[:, 0],
                    y=vertices[:, 1],
                    z=vertices[:, 2],
                    alphahull=0,
                    opacity=0.2,
                    color="#c4a5ff",
                    name="Measured rear clearance",
                    legendgroup="rear-clearance",
                    showlegend=show_rear_legend,
                    hovertemplate=op.id + "<extra>Measured rear clearance</extra>",
                )
            )
            show_rear_legend = False
        for env in revision.requirements.envelopes if envelopes else ():
            for placement in placements:
                lo = np.array(env.minimum) + placement
                hi = np.array(env.maximum) + placement
                vertices = np.array(
                    [
                        [lo[0], lo[1], lo[2]],
                        [hi[0], lo[1], lo[2]],
                        [hi[0], hi[1], lo[2]],
                        [lo[0], hi[1], lo[2]],
                        [lo[0], lo[1], hi[2]],
                        [hi[0], lo[1], hi[2]],
                        [hi[0], hi[1], hi[2]],
                        [lo[0], hi[1], hi[2]],
                    ]
                )
                fig.add_trace(
                    go.Mesh3d(
                        x=vertices[:, 0],
                        y=vertices[:, 1],
                        z=vertices[:, 2],
                        alphahull=0,
                        opacity=0.15,
                        color="#ef6262",
                        name=env.purpose,
                    )
                )
    fig.update_layout(
        height=510,
        margin=dict(l=0, r=0, b=0, t=5),
        paper_bgcolor="#101820",
        font_color="#dce5ed",
        scene=dict(
            aspectmode="data",
            camera=dict(up=dict(x=0, y=1, z=0))
            if revision and revision.plan.parameters.get("up_axis") == "Y"
            else {},
            xaxis_title="X · mm",
            yaxis_title="Y · mm",
            zaxis_title="Z · mm",
        ),
        uirevision=analysis.source_hash,
        legend=dict(orientation="h"),
    )
    return fig


def hole_picker_figure(analysis, picks):
    """Show every measured candidate in source coordinates, including ambiguous faces."""
    fig = go.Figure()
    add_mesh(fig, analysis.mesh, "#9ba9b9", "Uploaded STEP", hoverinfo="skip")
    theta = np.linspace(0, 2 * np.pi, 49)
    colors = hole_size_colors(analysis)
    for interface in analysis.interfaces:
        basis = np.asarray([interface.x, interface.y, interface.z])
        for hid, center, diameter in zip(
            interface.hole_ids, interface.centers, interface.diameters
        ):
            selected = interface.id == picks.interface_id and hid in picks.hole_ids
            compatible = not picks.hole_ids or interface.id == picks.interface_id
            color = colors[hole_size_key(diameter)]
            # Offset toward the outside of the face to avoid depth fighting with the mesh.
            c = np.asarray(center) + [0, 0, -0.06]
            ring = c + np.column_stack(
                (
                    diameter / 2 * np.cos(theta),
                    diameter / 2 * np.sin(theta),
                    np.zeros(49),
                )
            )
            world = ring @ basis + interface.origin
            point = c @ basis + interface.origin
            fig.add_trace(
                go.Scatter3d(
                    x=[*world[:, 0], None, point[0]],
                    y=[*world[:, 1], None, point[1]],
                    z=[*world[:, 2], None, point[2]],
                    mode="lines+markers",
                    line=dict(color=color, width=8 if selected else 5),
                    marker=dict(
                        color=[color] * 50 + ["#ffffff" if selected else color],
                        size=[3] * 50 + [20],
                        symbol=["circle"] * 50 + ["diamond" if selected else "circle"],
                    ),
                    opacity=1 if compatible else 0.25,
                    visible=compatible,
                    meta=dict(
                        interface_id=interface.id, hole_id=hid, selected=selected
                    ),
                    text=f"{hid} · {interface.id}<br>Measured bore: Ø {diameter:.3f} mm<br>"
                    "Screw thread size not inferred<br>"
                    + (
                        "Selected · remove using × in the list"
                        if selected
                        else "Click to select"
                        if compatible
                        else "Another face · clear selection to switch"
                    ),
                    hoverinfo="text",
                    name=hid,
                    showlegend=False,
                )
            )
    fig.update_layout(
        height=510,
        margin=dict(l=0, r=0, b=0, t=5),
        paper_bgcolor="#101820",
        font_color="#dce5ed",
        showlegend=False,
        scene=dict(
            aspectmode="data",
            xaxis_title="X · mm",
            yaxis_title="Y · mm",
            zaxis_title="Z · mm",
        ),
        uirevision=analysis.source_hash,
    )
    return fig
