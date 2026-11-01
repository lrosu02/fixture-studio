from pathlib import Path
from hashlib import sha256
from plotly.offline import get_plotlyjs
import streamlit as st
from .contracts import Record, MAX_DIM
from .viewer import assembly_figure
from .planning import patch_requirements, missing_questions
from .selection_ui import save_selection, rerun_selection
from .process_geometry import policy

LABELS = {
    "thickness": "Fixture thickness",
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

DESCRIPTIONS = {
    "thickness": "Thickness of the generated fixture stock. The uploaded part stays unchanged.",
    "margin": "Minimum fixture material extending beyond the part footprint.",
    "gap": "Space between neighboring parts when the fixture holds more than one.",
    "mount_height": "Height of the part's mounting reference above the top of the base.",
    "base_depth": "Front-to-back depth of the L-bracket's base foot.",
    "locating_clearance": "Extra space between the part and its locating wall.",
    "locating_wall": "Thickness of the wall surrounding the located part.",
    "locating_height": "Height of the wall surrounding the located part.",
    "retention_length": "Length of the cylindrical support along the part's axis.",
    "split_gap": "Gap separating the split-clamp halves.",
    "base_offset_x": "Position of the existing base along the mounting frame's X axis.",
    "base_offset_y": "Position of the existing base along the mounting frame's Y axis.",
    "base_rotation": "Rotation of the existing base in its mounting plane.",
    "process_radius": "Manufacturing corner size: chamfer for printing, radius/relief for machining. This is separate from rib-root fillets.",
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
    if v is not None:
        return float(v)
    if field == "process_radius":
        return float(policy(r)["corner_mm"])
    derived = plan.parameters.get(field + "_mm")
    return float(derived) if derived is not None else None


def value_label(r, plan, field):
    number = value(r, plan, field)
    if number is None:
        return "Automatic"
    unit = "°" if field == "base_rotation" else "mm"
    return ("Automatic · " if getattr(r, field) is None else "") + f"{number:g} {unit}"


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


def _save_thickness(project, key):
    error_key = "thickness-error-" + project.id
    try:
        number = st.session_state[key]
        if number <= 0:
            raise ValueError("Fixture thickness must be greater than zero.")
        updated = edit_dimension(project.requirements, "thickness", number)
        save_selection(
            project,
            updated,
            project.highlights,
            f"Set fixture thickness to {number:g} mm.",
        )
        st.session_state.pop(error_key, None)
    except (ValueError, OSError) as error:
        st.session_state[key] = project.requirements.thickness
        st.session_state[error_key] = str(error)


def thickness_controls(project, build):
    r = project.requirements
    st.markdown("**Fixture dimensions**")
    key = f"fixture-thickness-{project.id}-{r.thickness}"
    st.number_input(
        "Fixture thickness (mm)",
        min_value=0.0,
        max_value=float(MAX_DIM),
        value=float(r.thickness),
        step=0.5,
        disabled="thickness" in r.locks,
        key=key,
        on_change=_save_thickness,
        args=(project, key),
        help="Stock thickness for the generated fixture. The uploaded part is unchanged.",
    )
    if error := st.session_state.get("thickness-error-" + project.id):
        st.error(error)
    if "thickness" in r.locks:
        st.caption(
                "Thickness is locked. Unlock it in Advanced or the fixture dimension editor."
        )
    if project.current:
        current = project.current.requirements.thickness
        changed = current != r.thickness
        if changed:
            st.caption(
                f"Showing the {current:g} mm fixture. Rebuild to use {r.thickness:g} mm."
            )
        questions = missing_questions(project.analysis, r)
        if st.button(
            "Rebuild with this thickness", disabled=not changed or bool(questions)
        ):
            build(project, r, f"Fixture thickness → {r.thickness:g} mm")
        if changed and questions:
            st.info("Before rebuilding: " + " ".join(questions))
    else:
        st.caption(
            "Thickness saves immediately and will be used when you generate the fixture."
        )


def dimension_figure(a, revision, selected_field=None):
    r = revision.requirements
    fig = assembly_figure(a, revision=revision, evidence=False)
    field = selected_field or "thickness"
    if field in fields(r):
        fig.add_annotation(
            text=f"Design setting · {LABELS[field]}: {value_label(r, revision.plan, field)}",
            x=0.02,
            y=0.98,
            xref="paper",
            yref="paper",
            showarrow=False,
            xanchor="left",
            yanchor="top",
            align="left",
            font=dict(size=11, color="#edf3f7"),
            bgcolor="#17242f",
            bordercolor="#3b5060",
            borderpad=7,
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
        st.info("Generate a fixture to edit its dimensions here.")
        return
    r = p.requirements
    context = p.id + rev.id + str(hash(r.model_dump_json()))
    choices = fields(r)
    selected = st.session_state.get("dimension-field-" + p.id, choices[0])
    choice_key = "dimension-choice-" + context
    preview_field = st.session_state.get(choice_key, selected)
    if preview_field not in choices:
        preview_field = choices[0]
    panel, preview = st.container(), st.container()
    with preview:
        st.caption(
            "Preview of the saved CAD. The caption identifies a design setting, "
            "not a measured edge. Choose a setting above to edit it."
        )
        component()(
            data=dict(
                figure=dimension_figure(p.analysis, rev, preview_field).to_json(),
                context=context,
                view_key=p.id,
                fields=[],
            ),
            key="dimensions-" + p.id,
            on_picked_change=lambda: None,
            height=580,
        )
    if selected not in choices:
        selected = choices[0]
    if st.session_state.get(choice_key) not in choices:
        st.session_state[choice_key] = selected
    with panel, st.container(border=True):
        st.markdown("**Edit a fixture dimension**")
        field = st.selectbox(
            "Dimension to edit",
            choices,
            index=choices.index(selected),
            format_func=LABELS.get,
            key=choice_key,
        )
        st.session_state["dimension-field-" + p.id] = field
        st.caption(DESCRIPTIONS[field])
        st.caption(
            "Built value: "
            + value_label(rev.requirements, rev.plan, field)
            + " · Saved setting: "
            + value_label(r, rev.plan, field)
        )
        number = st.number_input(
            "New value (degrees)" if field == "base_rotation" else "New value (mm)",
            value=value(r, rev.plan, field),
            key="dimension-value-" + context + field,
            disabled=field in r.locks,
            help="Enter the target value, then rebuild to update and check the fixture CAD.",
        )
        if field in r.locks:
            st.info(
                "This dimension is locked. Open Dimension lock below to unlock it before editing."
            )
        questions = missing_questions(p.analysis, r)
        if st.button(
            "Apply dimension and rebuild",
            type="primary",
            disabled=field in r.locks or number is None or bool(questions),
        ):
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
            "Rebuild runs the normal CAD checks and review. A failed change keeps the last valid fixture."
        )
        if questions:
            st.info("Before rebuilding: " + " ".join(questions))
        with st.expander("Dimension lock", expanded=False):
            st.caption(
                "A locked value is protected from manual and assistant changes until you unlock it."
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
                    save_selection(
                        p,
                        patch_requirements(r, {"locks": locks}),
                        p.highlights,
                        f"Dimension lock: {LABELS[field]} {'locked' if locked else 'unlocked'}.",
                    )
                    rerun_selection()
                except (ValueError, OSError) as error:
                    st.error(str(error))
