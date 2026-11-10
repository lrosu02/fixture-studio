"""Pure, shared design-state projection. No UI, kernel, disk or provider calls.

Saved requirements, published CAD and conversation readiness are independent.
Do not infer one from another (or from whether a ZIP has been downloaded).
"""

from enum import StrEnum
from typing import Literal

from .contracts import Record
from .questions import clean_questions, merge_questions


class DesignPhase(StrEnum):
    SETUP = "setup"
    CLARIFYING = "clarifying"
    READY = "ready"
    CHANGES = "changes_pending"
    REVIEW = "review"
    RECOVERY = "recovery"


class CadState(StrEnum):
    ABSENT = "absent"
    CURRENT = "current"
    OUTDATED = "outdated"


class WorkspaceMode(StrEnum):
    ASSEMBLY = "assembly"
    FACE = "face"
    HOLES = "holes"
    ACCESS = "access"
    OPENINGS = "openings"


class QuestionState(Record):
    """The last explicit question owner; an empty state supersedes old history."""

    source: Literal["none", "planner", "review"] = "none"
    questions: tuple[str, ...] = ()
    revision_id: str | None = None


class WorkflowState(Record):
    phase: DesignPhase
    cad: CadState
    revision_id: str | None
    questions: tuple[str, ...]
    question_source: str
    error: str | None
    review_outcome: str | None
    pending_openings: int
    can_generate: bool
    can_export_saved_revision: bool
    next_actions: tuple[str, ...]


def active_questions(project, setup=()):
    """New snapshots have explicit ownership; old snapshots retain their semantics."""
    state = getattr(project, "clarification", None)
    if state is not None:
        return merge_questions(
            state.questions if getattr(project, "stage", None) == "clarifying" else (),
            setup,
        )
    attempt = getattr(project, "last_planner_attempt", None) or {}
    action = attempt.get("action") or {}
    clarifying = getattr(project, "stage", None) == "clarifying" and not getattr(
        project, "error", None
    )
    current = clean_questions(action.get("questions", ()) or ()) if clarifying else ()
    if clarifying and not current:
        revision = getattr(project, "current", None)
        latest = next(
            (
                record
                for record in reversed(getattr(project, "feedback", ()) or ())
                if revision
                and getattr(getattr(record, "build", None), "revision_id", None)
                == getattr(revision, "id", None)
            ),
            None,
        )
        if getattr(latest, "outcome", None) == "needs_input":
            current = clean_questions(
                getattr(getattr(latest, "review", None), "questions", ()) or ()
            )
    return merge_questions(current, setup)


def set_questions(project, source="none", questions=(), revision_id=None):
    """Explicit planner/review/restore event; never search transcript text for state."""
    project.clarification = QuestionState(
        source=source,
        questions=clean_questions(questions),
        revision_id=revision_id,
    )


def workflow_state(project, setup=None):
    """Authoritative readiness for UI and agents; availability is not authorization.

    Generate still requires an explicit request and the compiler's full validation.
    Export availability means the saved CAD exists, not that STEP is already prepared.
    """
    requirements = getattr(project, "requirements", None)
    revision = getattr(project, "current", None)
    if setup is None:
        from .planning import missing_questions

        setup = missing_questions(project.analysis, requirements)
    questions = active_questions(project, setup)
    error = getattr(project, "error", None)
    pending = bool(revision and revision.requirements != requirements)
    cad = (
        CadState.OUTDATED
        if pending
        else CadState.CURRENT
        if revision
        else CadState.ABSENT
    )
    started = bool(
        revision
        or getattr(project, "last_planner_attempt", None)
        or getattr(requirements, "purpose", None)
    )
    # Minimal presentation test doubles have no requirements; do not invent setup.
    phase = (
        DesignPhase.RECOVERY
        if error
        else DesignPhase.SETUP
        if requirements is not None and not started
        else DesignPhase.CLARIFYING
        if questions
        else DesignPhase.CHANGES
        if pending
        else DesignPhase.REVIEW
        if revision
        else DesignPhase.READY
    )
    review = next(
        (
            f
            for f in reversed(getattr(project, "feedback", ()) or ())
            if revision and f.build.revision_id == revision.id
        ),
        None,
    )
    can_generate = not questions and phase != DesignPhase.SETUP
    actions = (
        ["answer_questions"]
        if questions
        else ["edit_brief"]
        if phase == DesignPhase.SETUP
        else []
    )
    if can_generate:
        actions.append("generate")
    if error:
        actions.append("retry_or_revise")
    pending_openings = sum(
        opening.needs_placement
        for opening in getattr(requirements, "fixture_openings", ())
    )
    if revision:
        actions.extend(
            ("request_revision", "restore_revision", "export_saved_revision")
        )
        if pending_openings:
            actions.append(
                "place_openings_after_generation" if pending else "place_openings"
            )
    clarification = getattr(project, "clarification", None)
    return WorkflowState(
        phase=phase,
        cad=cad,
        revision_id=revision.id if revision else None,
        questions=questions,
        question_source=(
            "none"
            if not questions
            else clarification.source
            if clarification
            and clarification.questions
            and project.stage == "clarifying"
            else "requirements"
            if clarification
            else "legacy_or_requirements"
        ),
        error=error,
        review_outcome=review.outcome if review else None,
        pending_openings=pending_openings,
        can_generate=can_generate,
        can_export_saved_revision=revision is not None,
        next_actions=tuple(actions),
    )


def presentation(state):
    """All user-facing workflow entry points use the same phase and next step."""
    return {
        DesignPhase.SETUP: (
            "Describe the fixture",
            "Start with Fixture goal and motion, access and load notes in Design conversation.",
            1,
        ),
        DesignPhase.CLARIFYING: (
            "Design questions",
            "Answer the questions below together in one reply.",
            1,
        ),
        DesignPhase.READY: (
            "Choose a fixture concept",
            "Review the proposals below and generate the approach you want.",
            2,
        ),
        DesignPhase.CHANGES: (
            "Review your changes",
            "Choose Generate on a fixture concept to apply your saved changes to the CAD.",
            2,
        ),
        DesignPhase.REVIEW: (
            "Review the fixture",
            "Inspect the model, request a change, or prepare a STEP download.",
            3,
        ),
        DesignPhase.RECOVERY: (
            "Resolve the last attempt",
            "Review the error below, then retry or describe a change.",
            1 if state.questions else 2,
        ),
    }[state.phase]
