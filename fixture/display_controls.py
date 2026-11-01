"""Preview-only controls; never change requirements or generate geometry."""

import streamlit as st


def render_display_controls(project, selecting):
    def key(name):
        return f"workspace-view-{project.id}-{name}"

    for name, default in (
        ("source", True),
        ("fixture", True),
        ("evidence", True),
        ("dimensions", False),
        ("envelopes", False),
        ("edit", False),
        ("compare", False),
    ):
        st.session_state.setdefault(key(name), default)
    editing = st.session_state[key("edit")] and not selecting
    preview_disabled = selecting or editing
    with st.expander("Display settings", expanded=False):
        if selecting:
            st.caption(
                "Selection tools show the uploaded part. Return to an assembly or fixture view to change the display."
            )
        elif editing:
            st.caption(
                "The dimension editor uses its own preview. Turn off dimension editing to change objects or overlays."
            )
        st.markdown("**Objects**")
        objects = st.columns(2)
        source = objects[0].checkbox(
            "Uploaded part",
            key=key("source"),
            disabled=preview_disabled,
            help="The original STEP geometry, shown for reference.",
        )
        fixture = objects[1].checkbox(
            "Generated fixture",
            key=key("fixture"),
            disabled=preview_disabled or project.current is None,
            help="The saved CAD revision. Edited requirements appear after rebuilding.",
        )
        st.markdown("**Overlays**")
        evidence = st.checkbox(
            "Mounting hole highlights",
            key=key("evidence"),
            disabled=preview_disabled,
            help="Highlight measured mounting bores. This does not select or remove holes.",
        )
        dimensions = st.checkbox(
            "Design values (reference)",
            key=key("dimensions"),
            disabled=preview_disabled or project.current is None,
            help="Show the saved revision's design values. Use the dimension editor to change them.",
        )
        envelopes = st.checkbox(
            "Keep-clear areas",
            key=key("envelopes"),
            disabled=preview_disabled,
            help="Show reserved space and access regions for cables, tools or moving parts.",
        )
        st.markdown("**Edit & compare**")
        editing_dimensions = st.checkbox(
            "Edit fixture dimensions",
            key=key("edit"),
            disabled=selecting or project.current is None,
            help="Open the dimension editor. The uploaded part's measurements stay fixed.",
        )
        compare = st.checkbox(
            "Compare with previous revision",
            key=key("compare"),
            disabled=selecting
            or editing_dimensions
            or not (project.current and project.current.parent),
            help="Overlay the parent of the displayed revision.",
        )
        if project.current is None:
            st.caption(
                "Generate a fixture to enable its preview, dimension editor and revision comparison."
            )
    return dict(
        source=source,
        fixture=fixture,
        evidence=evidence,
        dimensions=dimensions,
        envelopes=envelopes,
        editing_dimensions=editing_dimensions,
        compare=compare,
    )
