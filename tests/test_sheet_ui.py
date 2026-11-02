from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest

from fixture.manufacturing import SHEET_METAL, CUSTOM
from fixture.project import Project
from tests.test_geometry import ready


HARNESS = """
import streamlit as st
from fixture.controls import manufacturing_controls, fillet_controls
manufacturing_controls(st.session_state.project)
fillet_controls(st.session_state.project)
"""


@pytest.fixture(autouse=True)
def forbid_generation(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("UI saves must not generate CAD")

    monkeypatch.setattr(Project, "generate", fail)


def app(**updates):
    a, r = ready(fabrication=SHEET_METAL, **updates)
    project = Project(a, r)
    ui = AppTest.from_string(HARNESS, default_timeout=30)
    ui.session_state.project = project
    return ui.run(), project


def select(ui, label):
    return next(x for x in ui.selectbox if x.label == label)


def number(ui, label):
    return next(x for x in ui.number_input if x.label == label)


def button(ui, label):
    return next(x for x in ui.button if x.label == label)


def test_sheet_option_appears_after_saving_method_and_preserves_fillet_settings():
    a, r = ready(fabrication="Machined stock", rib_fillet_radius=0.7)
    p = Project(a, r)
    ui = AppTest.from_string(HARNESS, default_timeout=30)
    ui.session_state.project = p
    ui.run()
    assert not any(x.label == "Tabs & welded joints" for x in ui.expander)
    select(ui, "Manufacturing method").select(SHEET_METAL).run()
    assert p.requirements.fabrication == "Machined stock"
    button(ui, "Save manufacturing").click().run()
    assert not ui.exception and p.requirements.fabrication == SHEET_METAL
    assert any(x.label == "Tabs & welded joints" for x in ui.expander)
    assert not any(x.label == "Rib-to-base fillets" for x in ui.expander)
    assert p.requirements.auto_rib_fillets and p.requirements.rib_fillet_radius == 0.7
    assert not p.revisions
    select(ui, "Manufacturing method").select("Machined stock").run()
    button(ui, "Save manufacturing").click().run()
    assert any(x.label == "Rib-to-base fillets" for x in ui.expander)
    assert p.requirements.auto_rib_fillets and p.requirements.rib_fillet_radius == 0.7


def test_sheet_joint_save_has_explicit_units_and_automatic_width():
    ui, p = app(sheet_tab_width=8.0)
    before = p.requirements
    number(ui, "Slot clearance per side (mm)").set_value(0.25)
    number(ui, "Tab width (mm; 0 = automatic)").set_value(0)
    number(ui, "Tabs per tabbed joint").set_value(3)
    number(ui, "Weld root gap (mm)").set_value(0.1)
    button(ui, "Save assembly joints").click().run()
    assert not ui.exception
    r = p.requirements
    assert (
        r.sheet_slot_clearance,
        r.sheet_tab_width,
        r.sheet_tab_count,
        r.sheet_root_gap,
    ) == (0.25, None, 3, 0.1)
    assert r.provenance["sheet_slot_clearance"] == "user"
    assert (
        r.thickness == before.thickness
        and r.mounting_hole_ids == before.mounting_hole_ids
    )
    assert not p.revisions
    saved = Project.load(f"artifacts/{p.id}/project.json")
    assert saved.requirements == r
    assert (
        any("per side" in x.value for x in ui.caption)
        or "per side" in p.messages[-1]["content"]
    )
    assert any("separate flat panels" in x.value for x in ui.caption)
    assert any("load capacity" in x.value for x in ui.caption)


def test_weld_only_preserves_saved_tab_settings():
    ui, p = app(sheet_tab_width=7.0, sheet_tab_count=4, sheet_slot_clearance=0.3)
    select(ui, "Panel joint method").select("weld_only").run()
    assert not any(x.label == "Tabs per tabbed joint" for x in ui.number_input)
    button(ui, "Save assembly joints").click().run()
    assert not ui.exception and p.requirements.sheet_joint_style == "weld_only"
    assert (
        p.requirements.sheet_tab_width,
        p.requirements.sheet_tab_count,
        p.requirements.sheet_slot_clearance,
    ) == (7.0, 4, 0.3)
    select(ui, "Panel joint method").select("tab_slot_weld").run()
    assert number(ui, "Tab width (mm; 0 = automatic)").value == 7.0
    assert number(ui, "Tabs per tabbed joint").value == 4


def test_sheet_joint_locks_disable_inputs_without_changing_values():
    fields = (
        "sheet_joint_style",
        "sheet_tab_width",
        "sheet_tab_count",
        "sheet_slot_clearance",
        "sheet_root_gap",
        "fabrication",
    )
    ui, p = app(locks=fields)
    before = p.requirements
    assert select(ui, "Panel joint method").disabled
    assert select(ui, "Manufacturing method").disabled
    assert button(ui, "Save manufacturing").disabled
    for label in (
        "Slot clearance per side (mm)",
        "Tab width (mm; 0 = automatic)",
        "Tabs per tabbed joint",
        "Weld root gap (mm)",
    ):
        assert number(ui, label).disabled
    button(ui, "Save assembly joints").click().run()
    assert not ui.exception and p.requirements == before and not p.messages
    advanced = AppTest.from_string(
        """
import streamlit as st
from fixture.controls import requirement_controls
requirement_controls(st.session_state.project)
""",
        default_timeout=30,
    )
    advanced.session_state.project = p
    advanced.run()
    assert not advanced.exception
    locks = next(
        x for x in advanced.multiselect if x.label == "Lock requirement values"
    )
    assert set(fields) <= set(locks.options)


def test_joint_save_failure_rolls_back_requirements_and_activity(monkeypatch):
    ui, p = app()
    p.error, p.stage = "Retained earlier error", "presented"
    before, messages = p.requirements, deepcopy(p.messages)

    def fail_save(self):
        raise OSError("Injected sheet save failure")

    monkeypatch.setattr(Project, "save", fail_save)
    number(ui, "Tabs per tabbed joint").set_value(4)
    button(ui, "Save assembly joints").click().run()
    assert not ui.exception and p.requirements == before and p.messages == messages
    assert p.error == "Retained earlier error" and p.stage == "presented"
    assert any("Injected sheet save failure" in x.value for x in ui.error)


def test_custom_method_fallback_is_not_replaced_by_sheet_option():
    a, r = ready(fabrication="Waterjet and manual assembly")
    p = Project(a, r)
    ui = AppTest.from_string(HARNESS, default_timeout=30)
    ui.session_state.project = p
    ui.run()
    assert not ui.exception and select(ui, "Manufacturing method").value == CUSTOM
    assert (
        next(x for x in ui.text_input if x.label == "Custom manufacturing method").value
        == r.fabrication
    )
    assert not any(x.label == "Tabs & welded joints" for x in ui.expander)


def test_method_save_failure_keeps_previous_method_and_choices(monkeypatch):
    a, r = ready(fabrication="Machined stock", rib_fillet_radius=0.7)
    p = Project(a, r)
    ui = AppTest.from_string(HARNESS, default_timeout=30)
    ui.session_state.project = p
    ui.run()
    before, messages = p.requirements, deepcopy(p.messages)

    def fail_save(self):
        raise OSError("Injected method save failure")

    monkeypatch.setattr(Project, "save", fail_save)
    select(ui, "Manufacturing method").select(SHEET_METAL).run()
    button(ui, "Save manufacturing").click().run()
    assert not ui.exception and p.requirements == before and p.messages == messages
    assert any("Injected method save failure" in x.value for x in ui.error)


def test_new_lock_discards_an_unsaved_draft_for_that_requirement():
    ui, p = app(sheet_tab_count=2)
    number(ui, "Tabs per tabbed joint").set_value(4).run()
    assert p.requirements.sheet_tab_count == 2
    p.requirements = p.requirements.model_copy(update={"locks": ("sheet_tab_count",)})
    ui.run()
    assert not ui.exception
    assert number(ui, "Tabs per tabbed joint").disabled
    assert number(ui, "Tabs per tabbed joint").value == 2


def test_saved_sheet_alias_uses_the_same_backend_method_detection():
    a, r = ready(fabrication="Sheet metal")
    p = Project(a, r)
    ui = AppTest.from_string(HARNESS, default_timeout=30)
    ui.session_state.project = p
    ui.run()
    assert not ui.exception and select(ui, "Manufacturing method").value == SHEET_METAL
    assert any(x.label == "Tabs & welded joints" for x in ui.expander)
    assert not any(x.label == "Rib-to-base fillets" for x in ui.expander)
    assert p.requirements == r
