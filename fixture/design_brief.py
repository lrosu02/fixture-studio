"""Atomic guided brief persistence; planning and CAD stay explicit user actions."""

from .planning import patch_requirements, missing_questions
from .lifecycle import set_questions

ANSWER_LABELS = {
    "quantity": "Number of parts",
    "moving_components": "Moving or spinning components",
    "cable_routing": "Cable routing",
    "service_access": "Tool/service access",
    "motion_loads": "Loads and directions",
}


def started(project):
    return bool(
        project.current or project.last_planner_attempt or project.requirements.purpose
    )


def save_brief(project, text, answers):
    if set(answers) - ANSWER_LABELS.keys():
        raise ValueError("Unknown design brief field.")
    purpose = text.strip()
    if not purpose:
        raise ValueError("Describe what the fixture should do before starting.")
    if len(purpose) > 6000:
        raise ValueError("Keep the design brief under 6000 characters.")
    changes = {"purpose": purpose, "brief_answers_recorded": True}
    for key, value in answers.items():
        changes[key] = value.strip() or None if isinstance(value, str) else value
    changes = {
        k: v for k, v in changes.items() if v != getattr(project.requirements, k)
    }
    updated = patch_requirements(project.requirements, changes)
    message = (
        "Design brief: "
        + purpose
        + "\n\n"
        + "\n".join(
            f"{label}: {getattr(updated, field) if getattr(updated, field) is not None else 'Not specified'}"
            for field, label in ANSWER_LABELS.items()
            if field != "cable_routing" or updated.cable_routing is not None
        )
    )
    if (
        updated == project.requirements
        and project.messages
        and project.messages[-1] == {"role": "user", "content": message}
    ):
        return message
    previous = (
        project.requirements,
        project.stage,
        project.error,
        list(project.messages),
        project.last_planner_attempt,
        project.clarification,
    )
    try:
        project.requirements = updated
        project.stage = (
            "clarifying"
            if missing_questions(project.analysis, updated)
            else "proposing"
        )
        project.error = None
        project.last_planner_attempt = (
            None  # Old clarification no longer describes this edited brief.
        )
        set_questions(project)
        project.messages.append({"role": "user", "content": message})
        project.save()
    except Exception:
        (
            project.requirements,
            project.stage,
            project.error,
            project.messages,
            project.last_planner_attempt,
            project.clarification,
        ) = previous
        raise
    return message
