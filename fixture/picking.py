"""Measured-hole picking. Browser events never provide CAD coordinates."""

from uuid import uuid4
from pydantic import Field
from .contracts import Record
from .planning import patch_requirements


class HolePicks(Record):
    context: str = Field(default_factory=lambda: uuid4().hex)
    interface_id: str | None = None
    hole_ids: tuple[str, ...] = ()


class HoleSelection(Record):
    context: str
    interface_id: str
    hole_ids: tuple[str, ...] = Field(min_length=1, max_length=1024)


def add_picked_holes(analysis, picks, event):
    """Idempotent additions: repeated or coalesced browser events cannot deselect."""
    click = HoleSelection.model_validate(event)
    if click.context != picks.context:
        raise ValueError(
            "This click belongs to an older selection. Click the hole again."
        )
    interface = next(
        (i for i in analysis.interfaces if i.id == click.interface_id), None
    )
    if interface is None or not set(click.hole_ids) <= set(interface.hole_ids):
        raise ValueError("The clicked hole is not in the current STEP analysis.")
    if picks.hole_ids and picks.interface_id != interface.id:
        raise ValueError(
            "Choose holes on one mounting face. Clear the selection to switch faces."
        )
    chosen = set(picks.hole_ids) | set(click.hole_ids)
    return picks.model_copy(
        update={
            "interface_id": interface.id if chosen else None,
            "hole_ids": tuple(h for h in interface.hole_ids if h in chosen),
        }
    )


def retain_picked_holes(picks, hole_ids):
    """Removal is an explicit list edit; a new context invalidates in-flight adds."""
    if not set(hole_ids) <= set(picks.hole_ids):
        raise ValueError("Only selected holes can be removed from this list.")
    holes = tuple(h for h in picks.hole_ids if h in hole_ids)
    return HolePicks(interface_id=picks.interface_id if holes else None, hole_ids=holes)


def use_picked_holes(analysis, requirements, picks, stationary):
    if not stationary:
        raise ValueError(
            "Confirm that the selected holes belong to the stationary mounting face."
        )
    interface = next(
        (i for i in analysis.interfaces if i.id == picks.interface_id), None
    )
    if not picks.hole_ids or interface is None:
        raise ValueError(
            "Click at least one detected hole before applying the selection."
        )
    if len(set(picks.hole_ids)) != len(picks.hole_ids) or any(
        h not in interface.hole_ids for h in picks.hole_ids
    ):
        raise ValueError("Selected holes must belong to one measured mounting face.")
    changes = {
        "interface_id": interface.id,
        "mounting_hole_ids": picks.hole_ids,
        "mounting_confirmed": True,
        "part_attachment": "screws",
    }
    if interface.id != requirements.interface_id:
        # Picking holes can also change the mounting frame, just like picking a face.
        changes["envelopes"] = ()
    return patch_requirements(requirements, changes)
