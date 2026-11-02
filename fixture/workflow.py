"""User-triggered planning and bounded generate/check/review/correct workflow."""

from uuid import uuid4
from datetime import datetime, timezone
from .agent import Action, apply_action, requests_geometry
from .contracts import DesignReview, FeedbackRecord
from .planning import missing_questions
from .review import repair_requirements, review_context, render_review

INVITE = "What would you like to change next?"


def plan_design(
    project, planner, text="", start=False, progress=lambda s: None, origin="user"
):
    """Start prepares a proposal; generation follows an explicit subsequent request."""
    original_requirements, original_highlights = (
        project.requirements,
        project.highlights,
    )
    project.last_planner_attempt = {
        "at": datetime.now(timezone.utc).isoformat(),
        "source_hash": project.analysis.source_hash,
        "action": None,
        "error": None,
    }
    if text.strip():
        project.messages.append({"role": "user", "content": text})
    if start:
        project.messages.append(
            {
                "role": "user",
                "content": "Start design using my brief, saved conversation, selected mounting face, part retention, any selected mounting holes and manufacturing method. First resolve unanswered moving/spinning components, swept space, cables/connectors, tool access and load questions. Reuse answers already saved; none and unknown are valid explicit answers. Then ask only the next relevant questions, or present a supported proposal for my review. Do not generate CAD yet.",
            }
        )
    try:
        progress("Planning with AI")
        action = Action.model_validate(
            planner(
                project.analysis,
                project.requirements,
                project.messages,
                project.current,
            )
        )
        # Store only the validated decision, never raw provider output/credentials.
        project.last_planner_attempt["action"] = action.model_dump(mode="json")
        if action.action == "unsupported":
            # A limitation response may not smuggle a substitute design into requirements.
            project.stage = "clarifying"
        else:
            candidate = apply_action(
                project.analysis, project.requirements, action, origin=origin
            )
            questions = missing_questions(project.analysis, candidate)
            project.requirements = candidate
            # The viewer uses source IDs; the planner also offers access namespaces.
            project.highlights = tuple(
                h.split(":", 1)[1] if h.startswith(("face:", "hole:", "rear:")) else h
                for h in action.highlight_ids
            )
            project.stage = (
                "clarifying" if questions or action.questions else "proposing"
            )
        project.messages.append(
            {
                "role": "assistant",
                "content": action.explanation
                + ("\n\n" + "\n\n".join(action.questions) if action.questions else ""),
            }
        )
        project.error = None
        if (
            not start
            and requests_geometry(action)
            and (questions := missing_questions(project.analysis, project.requirements))
        ):
            project.messages.append(
                {
                    "role": "assistant",
                    "content": "Before generating:\n\n" + "\n\n".join(questions),
                }
            )
            return False
        return not start and requests_geometry(action) and not action.questions
    except Exception as error:
        project.requirements, project.highlights = (
            original_requirements,
            original_highlights,
        )
        project.error = f"{type(error).__name__}: {error}"
        project.last_planner_attempt["error"] = project.error
        project.messages.append(
            {
                "role": "assistant",
                "content": "Planning failed: "
                + project.error[:1000]
                + "\n\nNo design changes were applied. Your saved choices and CAD are retained. Retry the request in the conversation.",
            }
        )
        project.stage = "presented" if project.current else "clarifying"
        return False
    finally:
        project.save()


def generate_with_feedback(
    project,
    reviewer,
    provider,
    requirements=None,
    change="Generate reviewed proposal",
    progress=lambda s: None,
):
    """No rerun scheduling: at most two builds and two reviews per explicit invocation."""
    candidate = requirements or project.requirements
    run_id = uuid4().hex
    for attempt in (1, 2):
        try:
            revision = project.generate(candidate, change, progress)
            project.messages.append({"role": "assistant", "content": revision.summary})
        except Exception:
            # Project captures this attempt's plan/checks/error and keeps the last valid CAD.
            revision = None
        build = project.last_attempt
        record = FeedbackRecord(
            run_id=run_id,
            attempt=attempt,
            provider=provider,
            build=build,
            outcome="offline",
        )
        if build.failure_kind == "cad_export":
            record = record.model_copy(
                update={
                    "outcome": "build_error",
                    "note": "CAD saving failed after bounded retries. Retry Generate. AI dimensional repair was skipped because this is a file-save error; requirements are unchanged.",
                }
            )
            project.feedback.append(record)
            project.messages.append({"role": "assistant", "content": record.note})
            project.save()
            return project.current
        if reviewer is None:
            record = record.model_copy(
                update={
                    "note": "Offline mode: geometric checks only; no AI review was requested."
                }
            )
            project.feedback.append(record)
            project.save()
            return project.current
        try:
            progress("Preparing generated views for AI review")
            images = render_review(project.analysis, revision) if revision else ()
            progress(
                "Reviewing CAD with AI"
                if revision
                else "Reviewing the failed attempt with AI"
            )
            context = review_context(project.analysis, build, 2 - attempt)
            review = DesignReview.model_validate(
                reviewer(context, project.messages, images)
            )
            record = record.model_copy(update={"review": review})
            if review.verdict == "accept" and build.error:
                raise ValueError(
                    "AI review accepted a failed build; that verdict was rejected. Resolve the reported geometry error."
                )
            project.messages.append(
                {
                    "role": "assistant",
                    "content": "AI review: "
                    + review.summary
                    + (
                        "\n\n" + "\n\n".join(review.questions)
                        if review.questions
                        else ""
                    ),
                }
            )
            if review.verdict == "accept":
                record = record.model_copy(update={"outcome": "accepted"})
            elif review.verdict == "needs_input":
                record = record.model_copy(update={"outcome": "needs_input"})
                project.stage = "clarifying"
            elif attempt == 2:
                record = record.model_copy(
                    update={
                        "outcome": "repair_limit",
                        "note": "The one-correction limit is reached. Choose the next change in chat.",
                    }
                )
            else:
                try:
                    candidate = repair_requirements(candidate, review)
                except ValueError as error:
                    record = record.model_copy(
                        update={"outcome": "repair_blocked", "note": str(error)}
                    )
                else:
                    record = record.model_copy(
                        update={
                            "outcome": "repair",
                            "note": "Applying one automatic correction to unlocked concept dimensions.",
                        }
                    )
                    change = "AI correction: " + review.summary
        except Exception as error:
            record = record.model_copy(
                update={
                    "outcome": "review_error",
                    "note": f"AI review incomplete: {type(error).__name__}: {error}. Generated CAD and the last valid revision are retained.",
                }
            )
        project.feedback.append(record)
        if record.note:
            project.messages.append({"role": "assistant", "content": record.note})
        if record.outcome != "repair":
            project.messages.append({"role": "assistant", "content": INVITE})
        project.save()
        if record.outcome != "repair":
            return project.current
        progress("Applying one AI correction")
    return project.current
