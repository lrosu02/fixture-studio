from streamlit.testing.v1 import AppTest

from fixture.manufacturing import SHEET_METAL
from fixture.project import Project
from tests.test_geometry import ready


HARNESS = """
import streamlit as st
from fixture.sheet_controls import sheet_controls
sheet_controls(st.session_state.project)
"""


def app(**changes):
    a, r = ready(fabrication=SHEET_METAL, composition="l_bracket", **changes)
    p = Project(a, r)
    ui = AppTest.from_string(HARNESS, default_timeout=30)
    ui.session_state.project = p
    return ui.run(), p


def construction(ui):
    return next(x for x in ui.selectbox if x.label == "Sheet construction")


def save(ui):
    return next(x for x in ui.button if x.label == "Save assembly joints").click().run()


def test_bent_settings_save_only_and_cut_mode_retains_bend_radius():
    ui, p = app()
    assert construction(ui).value == "cut_weld"
    construction(ui).select("bent_weld").run()
    radius = next(
        x for x in ui.number_input if x.label.startswith("Inside bend radius")
    )
    assert radius.value == 0
    radius.set_value(4.0)
    save(ui)
    assert not ui.exception and p.requirements.sheet_construction == "bent_weld"
    assert p.requirements.sheet_bend_radius == 4.0 and not p.revisions
    construction(ui).select("cut_weld").run()
    save(ui)
    assert p.requirements.sheet_bend_radius == 4.0
    construction(ui).select("bent_weld").run()
    assert (
        next(
            x for x in ui.number_input if x.label.startswith("Inside bend radius")
        ).value
        == 4.0
    )


def test_automatic_radius_and_bend_locks_are_explicit():
    ui, p = app(
        sheet_construction="bent_weld",
        locks=("sheet_construction", "sheet_bend_radius"),
    )
    assert not ui.exception and construction(ui).disabled
    radius = next(
        x for x in ui.number_input if x.label.startswith("Inside bend radius")
    )
    assert radius.disabled and radius.value == 0
    assert any("equal to sheet thickness" in x.value for x in ui.caption)
    assert p.requirements.sheet_bend_radius is None and not p.revisions
