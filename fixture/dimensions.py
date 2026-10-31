from pathlib import Path
from hashlib import sha256
import numpy as np
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
import streamlit as st
from .contracts import Record
from .viewer import assembly_figure
from .planning import patch_requirements

LABELS = {
    "thickness": "Stock thickness",
    "gap": "Part gap",
    "margin": "Minimum stock margin",
    "mount_height": "Mount height",
    "base_depth": "Base depth",
    "locating_clearance": "Fit clearance",
    "locating_wall": "Support wall",
    "locating_height": "Wall height",
    "retention_length": "Support length",
    "split_gap": "Clamp split gap",
    "base_offset_x": "Base offset X",
    "base_offset_y": "Base offset Y",
    "base_rotation": "Base rotation",
    "process_radius": "Manufacturing corner size",
}
SHORT_LABELS = {
    "thickness": "Stock",
    "margin": "Margin",
    "gap": "Gap",
    "mount_height": "Height",
    "base_depth": "Base depth",
    "locating_clearance": "Fit",
    "locating_wall": "Wall",
    "locating_height": "Wall height",
    "retention_length": "Seat length",
    "split_gap": "Split",
    "base_offset_x": "Base X",
    "base_offset_y": "Base Y",
    "base_rotation": "Base angle",
    "process_radius": "Corner",
}


class DimensionClick(Record):
    context: str
    field: str


def fields(r):
    chosen = ["thickness", "margin"]
    if (r.quantity or 1) > 1:
        chosen.append("gap")
    if r.composition in ("l_bracket", "bridge"):
        chosen.append("mount_height")
    if r.composition == "l_bracket":
        chosen.append("base_depth")
    if r.part_attachment != "screws":
        chosen += ["locating_clearance", "locating_wall"]
    if r.part_attachment in ("cradle", "strap", "nest"):
        chosen.append("locating_height")
    if r.part_attachment in ("saddle", "collar", "split_clamp"):
        chosen.append("retention_length")
    if r.part_attachment == "split_clamp":
        chosen.append("split_gap")
    if r.base_mount:
        chosen += ["base_offset_x", "base_offset_y", "base_rotation"]
    if r.manufacturing_features:
        chosen.append("process_radius")
    return chosen


def value(r, plan, field):
    v = getattr(r, field)
    return float(v if v is not None else plan.parameters.get(field + "_mm", 0))


def select_dimension(r, event, context):
    event = DimensionClick.model_validate(event)
    if event.context != context or event.field not in fields(r):
        raise ValueError(
            "This dimension click belongs to an old or unsupported design."
        )
    return event.field


def edit_dimension(r, field, number):
    if field not in fields(r):
        raise ValueError("Unsupported dimension.")
    return patch_requirements(r, {field: float(number)})


def dimension_figure(a, revision):
    r = revision.requirements
    fig = assembly_figure(a, revision=revision, evidence=False)
    points = np.concatenate([np.array(m.vertices) for m in revision.meshes.values()])
    lo, hi = points.min(axis=0), points.max(axis=0)
    span = np.maximum(hi - lo, 1)
    for n, field in enumerate(fields(r)):
        # Labels are editable design values, not measurements read from pixels.
        point = (
            lo[0] + span[0] * (n % 3) / 2,
            lo[1] - span[1] * (0.12 + 0.18 * (n // 3)),
            hi[2] + span[2] * 0.1,
        )
        locked = field in r.locks
        fig.add_trace(
            go.Scatter3d(
                x=[point[0]],
                y=[point[1]],
                z=[point[2]],
                mode="markers+text",
                marker=dict(size=9, color="#8c97a4" if locked else "#ffb454"),
                text=[
                    f"{SHORT_LABELS[field]}: {value(r, revision.plan, field):g} {'°' if field == 'base_rotation' else 'mm'}"
                    + (" · locked" if locked else "")
                ],
                textposition="top center",
                hoverinfo="text",
                hovertext=LABELS[field],
                meta={"dimension": field},
                showlegend=False,
            )
        )
    return fig


def component():
    source = Path(__file__).with_name("dimension_picker.js").read_text(encoding="utf-8")
    return registered_component(source)


@st.cache_resource(max_entries=4)
def registered_component(source):
    return st.components.v2.component(
        "dimension_editor_" + sha256(source.encode()).hexdigest()[:10],
        html='<div class="dimension-plot" style="height:560px;width:100%"></div>',
        js=get_plotlyjs() + "\n" + source,
        isolate_styles=False,
    )


def dimension_controls(p, build):
    rev = p.current
    if rev is None:
        st.info("Generate a fixture to edit its on-model dimensions.")
        return
    r = p.requirements
    context = p.id + rev.id + str(hash(r.model_dump_json()))
    choices = fields(r)
    result = component()(
        data=dict(
            figure=dimension_figure(p.analysis, rev).to_json(),
            context=context,
            view_key=p.id,
            fields=choices,
        ),
        key="dimensions-" + p.id,
        on_picked_change=lambda: None,
        height=580,
    )
    selected = st.session_state.get("dimension-field-" + p.id, choices[0])
    choice_key = "dimension-choice-" + context
    if result.picked:
        try:
            selected = select_dimension(r, result.picked, context)
            st.session_state[choice_key] = selected
        except ValueError as error:
            st.info(str(error))
    if selected not in choices:
        selected = choices[0]
    if st.session_state.get(choice_key) not in choices:
        st.session_state[choice_key] = selected
    field = st.selectbox(
        "Dimension to edit",
        choices,
        index=choices.index(selected),
        format_func=LABELS.get,
        key=choice_key,
    )
    st.session_state["dimension-field-" + p.id] = field
    number = st.number_input(
        "New value (degrees)" if field == "base_rotation" else "New value (mm)",
        value=value(r, rev.plan, field),
        key="dimension-value-" + context + field,
        disabled=field in r.locks,
    )
    locked = st.checkbox(
        "Lock this dimension",
        value=field in r.locks,
        key="dimension-lock-" + context + field,
    )
    if st.button("Save dimension lock"):
        try:
            locks = (
                tuple(sorted(set(r.locks) | {field}))
                if locked
                else tuple(k for k in r.locks if k != field)
            )
            p.requirements = patch_requirements(r, {"locks": locks})
            p.save()
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    if st.button("Apply dimension and rebuild", disabled=field in r.locks):
        try:
            updated = edit_dimension(r, field, number)
            p.messages.append(
                dict(
                    role="user",
                    content=f"Change {LABELS[field]} to {number:g}. Preserve locked dimensions and rebuild.",
                )
            )
            build(p, updated, f"{LABELS[field]} → {number:g}")
        except ValueError as error:
            st.error(str(error))
    st.caption(
        "Click an amber label to edit. Measured source holes stay fixed. Rebuilds preserve the last valid revision if a change conflicts."
    )
