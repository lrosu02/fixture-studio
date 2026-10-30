from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

MM_TOL = 0.01
VOL_REL_TOL = 0.001
MAX_DIM = 2000.0
MAX_OPS = 256
MAX_BODIES = 64
Vec = tuple[float, float, float]
Vec2 = tuple[float, float]
Positive = Annotated[float, Field(gt=0, le=MAX_DIM)]
Origin = Literal["measured", "user", "ai", "assumed", "derived"]
Composition = Literal["plate", "rails", "l_bracket", "bridge"]
PartAttachment = Literal["screws", "unselected", "cradle", "strap"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Mesh(Record):
    vertices: tuple[Vec, ...]
    triangles: tuple[tuple[int, int, int], ...]


class Feature(Record):
    id: str
    face_refs: tuple[int, ...]
    kind: Literal["plane", "hole"]
    position: Vec
    axis: Vec
    diameter: float | None = None
    evidence: str


class Interface(Record):
    id: str
    face_ref: int
    origin: Vec
    x: Vec
    y: Vec
    z: Vec  # inward normal; fixture occupies local z <= 0
    hole_ids: tuple[str, ...]
    centers: tuple[Vec, ...]
    diameters: tuple[float, ...]
    boundary: tuple[Vec, ...]
    exclusions: tuple[tuple[Vec, ...], ...]
    contact_radii: tuple[float, ...]
    contact_valid: tuple[bool, ...]
    contact_ok: bool
    confidence: str
    source_to_local: tuple[tuple[float, ...], ...]
    face_mesh: Mesh | None = None  # Exact trimmed face tessellation for selection.
    area_mm2: Annotated[float, Field(gt=0)] | None = None


class Analysis(Record):
    version: Literal[1, 2] = 2
    source_name: str
    source_hash: str
    original_units: tuple[str, ...]
    normalization: str
    selected_bodies: tuple[int, ...]
    body_count: int
    bounds: tuple[Vec, Vec]
    mesh: Mesh
    features: tuple[Feature, ...]
    interfaces: tuple[Interface, ...]
    limitations: tuple[str, ...]


class Envelope(Record):
    id: str
    minimum: Vec
    maximum: Vec
    purpose: str
    provenance: Origin = "user"

    @model_validator(mode="after")
    def valid_box(self):
        if any(b <= a for a, b in zip(self.minimum, self.maximum)):
            raise ValueError("Envelope must have positive finite volume.")
        if any(abs(x) > MAX_DIM for x in (*self.minimum, *self.maximum)):
            raise ValueError("Envelope exceeds workspace limits.")
        return self


class PrintSettings(Record):
    """User-specified manufacturing intent, not a slicer profile or allowables."""

    printer: Annotated[str, Field(max_length=200)] | None = None
    material_grade: Annotated[str, Field(max_length=300)] | None = None
    nozzle_diameter_mm: Annotated[float, Field(ge=0.1, le=2)] | None = None
    layer_height_mm: Annotated[float, Field(ge=0.02, le=1.5)] | None = None
    wall_count: Annotated[int, Field(ge=1, le=30)] | None = None
    infill_percent: Annotated[float, Field(ge=0, le=100)] | None = None
    orientation: Annotated[str, Field(max_length=1000)] | None = None
    supports: Literal["unknown", "allowed", "avoid"] | None = None
    notes: Annotated[str, Field(max_length=2000)] | None = None

    @model_validator(mode="after")
    def consistent_layers(self):
        if (
            self.nozzle_diameter_mm is not None
            and self.layer_height_mm is not None
            and self.layer_height_mm > self.nozzle_diameter_mm
        ):
            raise ValueError("Layer height must not exceed the nozzle diameter.")
        return self


class HoleFastenerChoice(Record):
    hole_ids: Annotated[tuple[str, ...], Field(min_length=1, max_length=128)]
    nominal: Annotated[str, Field(max_length=100)] | None = None
    clearance_diameter: Positive | None = None


class AccessSelection(Record):
    feature_id: str
    intent: Literal["through", "keep_clear"] = "through"
    padding: Annotated[float, Field(ge=0.3, le=20)] = 0.5
    reach: Annotated[float, Field(gt=0, le=500)] = 10


class BaseMount(Record):
    analysis: Analysis
    interface_id: str
    hole_ids: Annotated[tuple[str, ...], Field(min_length=1, max_length=128)]

    @model_validator(mode='after')
    def references(self):
        face = next((i for i in self.analysis.interfaces if i.id == self.interface_id), None)
        if face is None or len(set(self.hole_ids)) != len(self.hole_ids) or not set(self.hole_ids) <= set(face.hole_ids):
            raise ValueError('Choose measured holes on the selected base face.')
        return self


class Requirements(Record):
    purpose: str | None = None
    quantity: Annotated[int, Field(ge=1, le=24)] | None = None
    layout: Literal["row", "grid"] = "row"
    columns: Annotated[int, Field(ge=1, le=24)] = 3
    gap: Annotated[float, Field(ge=0, le=500)] = 12
    thickness: Positive = 6
    margin: Positive = 8
    max_width: Positive | None = None
    composition: Composition = "plate"
    mount_height: Positive | None = None
    base_depth: Positive | None = None
    reinforce: bool = True
    rear_clearance: Annotated[float, Field(ge=0.3, le=10)] = 0.3
    rear_passages: Annotated[tuple[str, ...], Field(max_length=32)] = ()
    through_access_required: bool = False
    interface_id: str | None = None
    mounting_hole_ids: tuple[str, ...] = ()
    mounting_confirmed: bool = False
    part_attachment: PartAttachment = "screws"
    locating_clearance: Annotated[float, Field(ge=0.3, le=10)] = 0.5
    locating_wall: Positive = 3
    locating_height: Positive | None = None
    strap_width: Positive | None = None
    strap_thickness: Positive | None = None
    clearance_diameter: Positive | None = None
    clearance_fit: Literal["fine", "medium", "coarse"] = "medium"
    nominal_fastener: str | None = None
    hole_fasteners: Annotated[tuple[HoleFastenerChoice, ...], Field(max_length=32)] = ()
    bench_fastener: str | None = None
    engagement: str | None = None
    surroundings: Literal["unknown", "clamp", "bolt"] = "unknown"
    bench_hole_diameter: Positive | None = None
    bench_hole_count: Annotated[int, Field(ge=1)] | None = None
    base_mount: BaseMount | None = None
    base_offset_x: Annotated[float, Field(ge=-1000, le=1000)] = 0
    base_offset_y: Annotated[float, Field(ge=-1000, le=1000)] = 0
    base_rotation: Annotated[float, Field(ge=-180, le=180)] = 0
    fabrication: str | None = None
    material: str | None = None
    print_settings: PrintSettings = Field(default_factory=PrintSettings)
    motion_loads: str | None = None
    access: str | None = None
    appearance: str | None = None
    envelopes: tuple[Envelope, ...] = ()
    access_selections: Annotated[tuple[AccessSelection, ...], Field(max_length=32)] = ()
    locks: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = (
        "Stock thickness, margin and gap are concept defaults until edited.",
    )
    assumptions_accepted: bool = False
    provenance: dict[str, Origin] = {}


class Proposal(Record):
    id: str
    interface_id: str
    composition: Composition
    title: str
    rationale: str
    surroundings: str
    unresolved: tuple[str, ...]
    checks: tuple[str, ...]
    reinforce: bool | None = None
    mount_height: Positive | None = None
    dimensions: dict[str, float | str] = {}


class Operation(Record):
    id: str
    kind: Literal["place", "stock", "support", "mount", "relief", "combine"]
    depends_on: tuple[str, ...] = ()
    frame: Literal["interface"] = "interface"
    body: str | None = None
    target: str | None = None
    other: str | None = None
    shape: Literal["box", "cylinder", "slot", "wedge", "prism"] = "box"
    profile: Annotated[tuple[Vec2, ...], Field(max_length=48)] = ()
    axis: Literal["x", "y", "z"] = "z"
    origin: Vec = (0, 0, 0)
    size: Vec = (1, 1, 1)
    interface_id: str | None = None
    instance_ids: tuple[int, ...] = ()
    hole_ids: tuple[str, ...] = ()
    diameter: Positive | None = None
    mode: Literal["union", "difference"] = "union"
    purpose: str = ""
    provenance: dict[str, Origin]

    @model_validator(mode="after")
    def bounds(self):
        if any(x <= 0 or x > MAX_DIM for x in self.size):
            raise ValueError("Operation dimensions must be positive and bounded.")
        if any(abs(x) > MAX_DIM for x in self.origin):
            raise ValueError("Operation origin exceeds workspace.")
        if not self.provenance:
            raise ValueError("Parameter provenance is required.")
        if self.shape == "prism":
            if self.axis != "z" or len(self.profile) < 3:
                raise ValueError(
                    "A prism needs a bounded convex XY profile and Z axis."
                )
            # Require a strictly convex, counter-clockwise, non-self-crossing loop.
            # Every vertex must lie on the left of every directed boundary edge.
            for n, p in enumerate(self.profile):
                q = self.profile[(n + 1) % len(self.profile)]
                if sum((q[k] - p[k]) ** 2 for k in (0, 1)) < 1e-12:
                    raise ValueError("Prism profile contains a duplicate vertex.")
                for k, v in enumerate(self.profile):
                    if k in (n, (n + 1) % len(self.profile)):
                        continue
                    if (q[0] - p[0]) * (v[1] - p[1]) - (q[1] - p[1]) * (
                        v[0] - p[0]
                    ) <= 1e-10:
                        raise ValueError(
                            "Prism profile must be strictly convex and counter-clockwise."
                        )
                if any(p[k] < -MM_TOL or p[k] > self.size[k] + MM_TOL for k in (0, 1)):
                    raise ValueError("Prism profile exceeds its bounded extent.")
        elif self.profile:
            raise ValueError("Only a prism may contain profile vertices.")
        return self


class FastenerClearance(Record):
    feature_id: str
    diameter: Positive
    nominal: str | None = None
    fit: Literal["fine", "medium", "coarse"] | None = None
    standard: str | None = None
    source_url: str | None = None
    source_verified: str | None = None
    basis: str
    origin: Origin


class Plan(Record):
    version: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9] = 1
    source_hash: str
    interface_id: str
    composition: Composition
    placements: tuple[Vec, ...]
    operations: Annotated[
        tuple[Operation, ...], Field(min_length=1, max_length=MAX_OPS)
    ]
    parameters: dict[str, float | str]
    clearances: tuple[FastenerClearance, ...] = ()

    @model_validator(mode="after")
    def graph(self):
        seen, bodies = set(), set()
        if not 1 <= len(self.placements) <= 24:
            raise ValueError("Placement count outside supported range.")
        for p in self.placements:
            if any(abs(x) > MAX_DIM for x in p) or abs(p[2]) > MM_TOL:
                raise ValueError(
                    "Placements must be bounded and in the attachment plane."
                )
        for op in self.operations:
            if op.id in seen or not set(op.depends_on) <= seen:
                raise ValueError("Duplicate operation, forward dependency or cycle.")
            if op.kind in ("stock", "support"):
                if not op.body or op.body in bodies:
                    raise ValueError("Stock/support must have a unique body ID.")
                if op.kind == "support" and op.target not in bodies:
                    raise ValueError("Missing support parent.")
                bodies.add(op.body)
            if op.kind in ("mount", "relief", "combine") and op.target not in bodies:
                raise ValueError("Operation references a missing body.")
            if op.kind == "combine":
                if op.other not in bodies or op.other == op.target:
                    raise ValueError("Invalid combine reference.")
                bodies.remove(op.other)
            if op.kind in ("place", "mount") and op.interface_id != self.interface_id:
                raise ValueError("Unknown interface reference.")
            if any(i < 0 or i >= len(self.placements) for i in op.instance_ids):
                raise ValueError("Unknown source instance.")
            seen.add(op.id)
            if len(bodies) > MAX_BODIES:
                raise ValueError("Body limit exceeded.")
        return self


class Check(Record):
    name: str
    features: tuple[str, ...] = ()
    method: str
    units: str = "mm"
    tolerance: float = MM_TOL
    measured: float | str
    result: Literal["passed", "failed", "inconclusive", "not_evaluated"]
    correction: str = ""


class Revision(Record):
    id: str
    parent: str | None
    changes: str
    requirements: Requirements
    plan: Plan
    artifact: str
    meshes: dict[str, Mesh]
    checks: tuple[Check, ...]
    metrics: dict[str, float]
    summary: str


class RepairChanges(Record):
    """Automatic review may adjust only unlocked concept dimensions."""

    gap: Annotated[float, Field(ge=0, le=500)] | None = None
    thickness: Positive | None = None
    margin: Positive | None = None


class DesignReview(Record):
    verdict: Literal["accept", "revise", "needs_input"]
    summary: str = Field(min_length=1, max_length=3000)
    findings: tuple[str, ...] = Field(max_length=8)
    changes: RepairChanges
    questions: tuple[str, ...] = Field(max_length=3)

    @model_validator(mode="after")
    def consistent_decision(self):
        edits = self.changes.model_dump(exclude_none=True)
        if (self.verdict == "revise") != bool(edits):
            raise ValueError(
                "Only a revise verdict may include nonempty repair changes."
            )
        return self


class BuildFeedback(Record):
    requirements: Requirements
    plan: Plan | None = None
    checks: tuple[Check, ...] = ()
    metrics: dict[str, float] = {}
    revision_id: str | None = None
    error: str | None = None
    failure_kind: Literal["design", "cad_export"] | None = None


class FeedbackRecord(Record):
    run_id: str
    attempt: Literal[1, 2]
    provider: str
    build: BuildFeedback
    review: DesignReview | None = None
    outcome: Literal[
        "accepted",
        "needs_input",
        "repair",
        "repair_blocked",
        "repair_limit",
        "review_error",
        "offline",
        "build_error",
    ]
    note: str = ""
