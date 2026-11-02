from streamlit.testing.v1 import AppTest
from pathlib import Path


def test_upload_slice():
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45
    ).run()
    assert not app.exception
    next(x for x in app.selectbox if x.label == "Bundled specimen").select(
        "multi_body.step"
    ).run()
    next(b for b in app.button if b.label == "Load example").click().run()
    next(x for x in app.selectbox if x.label == "Conversation mode").select(
        "Offline commands"
    ).run()
    assert not app.exception
    assert app.session_state["project"].analysis.interfaces
    assert app.session_state["project"].analysis.selected_bodies == (0, 1)
    assert not any(x.label == "Bodies representing one part" for x in app.multiselect)
    assert not any(x.label == "Analyze selected bodies" for x in app.button)
    assert not app.chat_input
    next(x for x in app.text_area if x.label == "Fixture goal").set_value(
        "A fixture for inspection"
    )
    next(b for b in app.button if b.label == "Save design brief").click().run()
    assert (
        app.session_state["project"]
        .messages[0]["content"]
        .startswith("Design brief: A fixture for inspection")
    )


def test_ui_full_generation_revision_restore(monkeypatch):
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45
    ).run()

    def button(label):
        return next(x for x in app.button if x.label == label)

    def text(label):
        return next(x for x in app.text_input if x.label == label)

    button("Load example").click().run()
    next(x for x in app.selectbox if x.label == "Conversation mode").select(
        "Offline commands"
    ).run()
    next(x for x in app.selectbox if x.label == "Manufacturing method").select(
        "Machined stock"
    ).run()
    button("Save manufacturing").click().run()
    for label, value in [
        ("Purpose", "Inspection"),
        (
            "Motion, attached loads and continuous operation (unknown accepted)",
            "unknown",
        ),
        ("Access needs (unknown accepted)", "rear tools"),
    ]:
        text(label).set_value(value)
    next(
        x for x in app.number_input if x.label.startswith("Custom mounting")
    ).set_value(3.5)
    next(x for x in app.selectbox if x.label == "Attachment to surroundings").select(
        "clamp"
    )
    next(x for x in app.checkbox if x.label.startswith("I confirm")).check()
    next(x for x in app.checkbox if x.label.startswith("I accept")).check()
    button("Save requirements").click().run()
    assert not app.exception
    button("Generate Common mounting plate").click().run()
    assert not app.exception
    first = app.session_state["project"].current
    assert first is not None
    button("Prepare STEP download").click().run()
    assert not app.exception
    assert any(x.label == "Download STEP (.step)" for x in app.get("download_button"))
    app.chat_input[0].set_value("quantity 6 grid 3 columns rear access").run()
    button("Generate Open parallel supports").click().run()
    assert not app.exception
    current = app.session_state["project"].current
    assert len(current.plan.placements) == 6 and current.plan.composition == "rails"
    next(x for x in app.selectbox if x.label == "Revision history").select(first.id)
    button("Restore selected revision").click().run()
    assert app.session_state["project"].current.id == first.id

    def timeout(*args, **kwargs):
        raise TimeoutError("Injected subscription timeout")

    monkeypatch.setattr("fixture.subscription.subscription_turn", timeout)
    next(x for x in app.selectbox if x.label == "Conversation mode").select(
        "ChatGPT subscription (Codex CLI)"
    ).run()
    app.chat_input[0].set_value("Change quantity to 2").run()
    assert not app.exception
    assert app.session_state["project"].current.id == first.id
    assert "timeout" in app.session_state["project"].error


def test_mouse_selection_apply_and_clear(monkeypatch):
    from types import SimpleNamespace

    events = []
    payloads = []

    def component(**kwargs):
        payloads.append(kwargs["data"])
        event = events.pop(0) if events else None
        if event:
            event.setdefault("sequence", kwargs["data"]["sequence"] + 1)
            if "hole_ids" in event:
                event["hole_ids"] = tuple(
                    dict.fromkeys((*kwargs["data"]["hole_ids"], *event["hole_ids"]))
                )
        return SimpleNamespace(picked=event)

    monkeypatch.setattr("fixture.mounting_picker.picker_component", lambda: component)
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45
    ).run()
    next(x for x in app.selectbox if x.label == "Bundled specimen").select(
        "mixed_hole_sizes.step"
    ).run()
    next(b for b in app.button if b.label == "Load example").click().run()
    original = app.session_state["project"]
    interface = next(
        i
        for i in original.analysis.interfaces
        if i.id == original.requirements.interface_id
    )
    next(b for b in app.button if b.label == "Select mounting holes").click().run()
    assert not app.exception
    picks = app.session_state["mounting_picks"]
    assert (
        not picks.hole_ids
    )  # Default interface is not automatic consent to select every hole.
    events.append(
        dict(
            context=picks.context,
            interface_id=interface.id,
            hole_ids=(interface.hole_ids[1],),
        )
    )
    app.run()
    assert not app.exception
    assert app.session_state["mounting_picks"].hole_ids == (interface.hole_ids[1],)
    another_size = next(
        h
        for h, d in zip(interface.hole_ids, interface.diameters)
        if abs(d - interface.diameters[1]) > 0.1
    )
    events.append(
        dict(context=picks.context, interface_id=interface.id, hole_ids=(another_size,))
    )
    app.run()
    chosen = app.session_state["mounting_picks"].hole_ids
    assert len(chosen) == 2
    assert any("Different measured hole sizes" in x.value for x in app.info)
    events.append(
        dict(context=picks.context, interface_id=interface.id, hole_ids=chosen)
    )
    app.run()
    assert app.session_state["mounting_picks"].hole_ids == chosen
    assert payloads[-1]["figure"] == payloads[-2]["figure"]
    assert payloads[-1]["context"] == payloads[-3]["context"]
    # The first accepted click also highlights its face. Later additions and
    # repeated events preserve the immutable figure, draft context and camera.
    next(
        x for x in app.multiselect if x.label == "Selected holes — remove with ×"
    ).unselect(another_size).run()
    chosen = (interface.hole_ids[1],)
    assert app.session_state["mounting_picks"].hole_ids == chosen
    assert app.session_state["mounting_picks"].context != picks.context
    assert (
        payloads[-1]["context"] != picks.context
    )  # Explicit removal does reset the draft.
    assert not app.exception
    r = app.session_state["project"].requirements
    assert r.mounting_hole_ids == chosen and r.mounting_confirmed
    assert app.session_state["pick_mode"]
    next(b for b in app.button if b.label == "Select mounting holes").click().run()
    next(b for b in app.button if b.label == "Clear hole selection").click().run()
    assert not app.session_state["mounting_picks"].hole_ids
    assert not app.session_state["project"].requirements.mounting_hole_ids
    assert app.session_state["project"].requirements.part_attachment == "unselected"


def test_start_design_questions_generate_feedback_and_no_repeat(monkeypatch):
    from fixture.agent import Action, Changes
    from fixture.contracts import DesignReview, RepairChanges

    calls, reviews = [], []

    def planner(a, r, messages, current):
        calls.append(messages[-1]["content"])
        if len(calls) == 1:
            return Action(
                action="clarify",
                changes=Changes(purpose="Inspection", quantity=2),
                questions=(
                    "Confirm the stationary mounting holes and fixture attachment.",
                ),
                highlight_ids=(),
                explanation="I will prepare a fixture around the measured part.",
            )
        return Action(
            action="propose",
            changes=Changes(
                interface_id=r.interface_id,
                mounting_confirmed=True,
                clearance_diameter=3.5,
                surroundings="clamp",
                fabrication="3D printing",
                motion_loads="unknown",
                access="rear access",
                assumptions_accepted=True,
            ),
            questions=(),
            highlight_ids=(),
            explanation="Review the common plate and parallel supports, then Generate.",
        )

    def reviewer(context, messages, images):
        reviews.append(context)
        assert images and context["attempt"]["revision_id"]
        return DesignReview(
            verdict="accept",
            summary="Measured holes and the requested count are retained.",
            findings=("Physical strength remains unassessed.",),
            changes=RepairChanges(),
            questions=(),
        )

    monkeypatch.setattr("fixture.subscription.subscription_turn", planner)
    monkeypatch.setattr("fixture.subscription.subscription_review", reviewer)
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45
    ).run()

    def button(label):
        return next(x for x in app.button if x.label == label)

    button("Load example").click().run()
    next(x for x in app.selectbox if x.label == "Conversation mode").select(
        "ChatGPT subscription (Codex CLI)"
    ).run()
    assert not next(
        x for x in app.expander if x.label.startswith("Advanced")
    ).proto.expanded
    next(x for x in app.text_area if x.label == "Fixture goal").set_value(
        "Hold two of these parts for inspection."
    )
    for label in (
        "Moving or spinning parts",
        "Tool and service access",
        "Loads and forces",
    ):
        next(x for x in app.text_area if x.label == label).set_value("unknown")
    button("Start design").click().run()
    assert len(calls) == 1 and not reviews
    assert app.session_state["project"].current is None
    app.run()
    assert len(calls) == 1
    app.chat_input[0].set_value(
        "I confirm the mounting holes. Use 3.5 mm fixture clearance, clamps and 3D printing. Loads unknown, rear access, and I accept the visible concept assumptions."
    ).run()
    assert not app.exception and len(calls) == 2
    button("Generate Common mounting plate").click().run()
    assert not app.exception and len(reviews) == 1
    assert app.session_state["project"].current.plan.parameters["quantity"] == 2
    assert any(x.label == "AI design feedback" for x in app.expander)
    assert not next(
        x for x in app.expander if x.label.startswith("Advanced")
    ).proto.expanded
    app.run()
    assert len(reviews) == 1 and len(app.session_state["project"].revisions) == 1
    next(x for x in app.selectbox if x.label == "Conversation mode").select(
        "Offline commands"
    ).run()
    assert not any(b.label == "Start design" for b in app.button)
    assert len(app.chat_input) == 1


def test_saved_project_selection_survives_new_project_files():
    from fixture.project import Project
    from tests.test_geometry import ready, ROOT

    a, r = ready()
    chosen = Project(a, r)
    chosen.save()
    path = ROOT / "artifacts" / chosen.id / "project.json"
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    next(x for x in app.selectbox if x.label == "Saved project").select(path).run()
    Project(a, r).save()
    app.run()
    assert next(x for x in app.selectbox if x.label == "Saved project").value == path
    next(x for x in app.button if x.label == "Resume project").click().run()
    assert not app.exception and app.session_state["project"].id == chosen.id


def test_ui_new_structures_and_grouped_choices():
    from fixture.project import Project
    from tests.test_geometry import ready, ROOT

    a, r = ready(
        composition="l_bracket",
        surroundings="bolt",
        bench_hole_diameter=3.2,
        mount_height=70.0,
    )
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45)
    app.session_state["project"] = Project(a, r)
    app.run()
    next(x for x in app.selectbox if x.label == "Conversation mode").select(
        "Offline commands"
    ).run()
    assert not app.exception
    assert any(x.value == "Model preview" for x in app.subheader)
    assert not next(
        x for x in app.expander if x.label == "Advanced — mounting evidence"
    ).proto.expanded
    assert not next(
        x for x in app.expander if x.label == "Advanced — requirements and assumptions"
    ).proto.expanded
    assert not any(x.label == "Finite access region" for x in app.expander)
    next(x for x in app.button if x.label == "Generate L-bracket").click().run()
    assert not app.exception
    first = app.session_state["project"].current
    assert first.plan.composition == "l_bracket" and first.metrics["body_count"] == 1
    app.chat_input[0].set_value("bridge mount_height 90").run()
    next(x for x in app.button if x.label == "Generate Bridge support").click().run()
    assert not app.exception
    current = app.session_state["project"].current
    assert current.parent == first.id and current.plan.composition == "bridge"
    assert current.plan.parameters["mount_height_mm"] == 90
    assert (
        current.requirements.mounting_hole_ids == first.requirements.mounting_hole_ids
    )
    assert current.metrics["hole_count"] == first.metrics["hole_count"]


def test_ui_proposed_screw_size_and_readable_compact_options():
    from fixture.project import Project
    from tests.test_geometry import ready, ROOT
    from fixture.fasteners import resolve_clearances

    a, r = ready("mixed_hole_sizes.step", clearance_diameter=None)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45)
    app.session_state["project"] = Project(a, r)
    app.run()
    selector = next(
        x for x in app.selectbox if x.label.startswith("Screw size · Ø3.000")
    )
    assert "#4" in selector.options and "M3" in selector.options
    selector.select("#4").run()
    next(x for x in app.button if x.label == "Apply screw sizes").click().run()
    assert not app.exception
    project = app.session_state["project"]
    assert "#4" in {c.nominal for c in resolve_clearances(a, project.requirements)}
    assert any(x.label == "Generate Open L-bracket" for x in app.button)
    assert any(x.label == "Generate Raised L-bracket" for x in app.button)
    assert not any("_" in x.label for x in app.button if x.label.startswith("Generate"))
    assert all(
        not x.proto.expanded for x in app.expander if x.label == "Design details"
    )
