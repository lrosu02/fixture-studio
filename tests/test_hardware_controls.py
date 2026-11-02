from streamlit.testing.v1 import AppTest

from fixture.contracts import HardwareChoice
from fixture.project import Project
from tests.test_geometry import ready, ROOT


HARNESS = """
import streamlit as st
from fixture.hardware_controls import hardware_controls
hardware_controls(st.session_state.project)
"""


def test_hardware_controls_save_restore_and_lock():
    a, r = ready(locks=("base_hardware",))
    project = Project(a, r)
    ui = AppTest.from_string(HARNESS, default_timeout=30)
    ui.session_state["project"] = project
    ui.run()
    assert not ui.exception
    assert not ui.expander[0].proto.expanded
    assert project.requirements.part_hardware == HardwareChoice()
    base = next(x for x in ui.selectbox if x.label == "Base fastener recess")
    assert base.disabled
    next(x for x in ui.selectbox if x.label == "Part fastener recess").select(
        "counterbore"
    ).run()
    next(
        x for x in ui.checkbox if x.label == "Custom part recess dimensions"
    ).check().run()
    next(
        x for x in ui.number_input if x.label.startswith("Part head diameter")
    ).set_value(7.5)
    next(
        x for x in ui.number_input if x.label.startswith("Part recess depth")
    ).set_value(2.5)
    next(
        x for x in ui.checkbox if x.label == "Check part screwdriver access"
    ).check().run()
    next(
        x for x in ui.number_input if x.label == "Part screwdriver diameter (mm)"
    ).set_value(8)
    next(
        x for x in ui.number_input if x.label == "Part screwdriver reach (mm)"
    ).set_value(30)
    next(
        x for x in ui.button if x.label == "Save fastener accommodations"
    ).click().run()
    assert not ui.exception and not ui.error
    expected = HardwareChoice(
        style="counterbore", diameter=7.5, depth=2.5, driver_diameter=8, driver_reach=30
    )
    assert project.requirements.part_hardware == expected
    assert project.requirements.base_hardware == r.base_hardware
    assert project.requirements.mounting_hole_ids == r.mounting_hole_ids
    assert not project.revisions
    loaded = Project.load(ROOT / "artifacts" / project.id / "project.json")
    assert loaded.requirements.part_hardware == expected
    assert loaded.requirements.base_hardware == r.base_hardware


def test_hardware_controls_require_explicit_tool_diameter():
    a, r = ready()
    project = Project(a, r)
    ui = AppTest.from_string(HARNESS, default_timeout=30)
    ui.session_state["project"] = project
    ui.run()
    next(
        x for x in ui.checkbox if x.label == "Check part screwdriver access"
    ).check().run()
    next(
        x for x in ui.button if x.label == "Save fastener accommodations"
    ).click().run()
    assert not ui.exception
    assert any(
        "positive part screwdriver diameter" in error.value for error in ui.error
    )
    assert project.requirements == r
