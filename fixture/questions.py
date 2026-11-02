"""Shared question cleanup for planning and restored conversation state."""

import re


# Only remove standalone invitations to press Generate. Questions containing
# dimensions, design choices or conditions must remain real blockers.
_GENERATE_INVITATION = re.compile(
    r"(?:would you like(?: me)? to|do you want(?: me)? to|shall (?:i|we)|"
    r"should (?:i|we)|may i|can i|are you ready to|ready to) "
    r"(?:generate|build|proceed with(?: generating| building)?)"
    r"(?: (?:the |this |a |your |accepted |approved )*"
    r"(?:cad(?: geometry| model| generation)?|fixture|design|model|proposal|revision|l-bracket))?"
    r"(?: now)?[?.!]*",
    re.IGNORECASE,
)


def clean_questions(questions):
    """Keep all substantive questions, deduplicated without changing their text."""
    result, seen = [], set()
    for question in questions:
        text = question.strip()
        key = re.sub(r"\s+", " ", text).casefold().rstrip("?.! ")
        if not text or key in seen or _GENERATE_INVITATION.fullmatch(text):
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


# Suppress only these generic setup prompts when a more specific question
# already asks for that information. Specific questions are never discarded,
# and the underlying required fields still block CAD until answered.
_SETUP_COVERAGE = (
    (
        "How many parts should it hold,",
        r"how many|number of (?:parts|motors|units)|\bquantity\b",
    ),
    (
        "Will anything move or rotate,",
        r"\bmov(?:e|es|ing|ement)\b|\brotat\w*|\bspinn\w*|swept|\btravel\b",
    ),
    (
        "Which tools, plugs or surfaces",
        r"\b(?:tools?|service|assembly)\b.*(?:access|clearance|reach)|reachable|accessible",
    ),
    (
        "Which tools or surfaces need",
        r"\b(?:tools?|service|assembly)\b.*(?:access|clearance|reach)|reachable|accessible",
    ),
    ("What loads and directions", r"\b(?:loads?|forces?|thrust|torque)\b"),
    (
        "Which manufacturing method",
        r"manufactur|fabricat|3d.print|\bcnc\b|machin|sheet.metal",
    ),
    (
        "Review and accept the visible concept assumptions",
        r"concept assumptions|\bdefaults\b|thickness.*margin.*(?:gap|spacing)",
    ),
)


def merge_questions(specific, required):
    """Prefer a specific prompt over a matching generic setup question."""
    specific = clean_questions(specific)
    remaining = []
    for question in required:
        pattern = next(
            (p for prefix, p in _SETUP_COVERAGE if question.startswith(prefix)), None
        )
        if pattern and any(re.search(pattern, q, re.IGNORECASE) for q in specific):
            continue
        remaining.append(question)
    return clean_questions((*specific, *remaining))
