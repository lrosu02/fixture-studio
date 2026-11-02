from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4
import io
import json
import zipfile
from .contracts import Analysis, Requirements, Revision, BuildFeedback, FeedbackRecord
from .intake import recommended_interface
from .planning import compile_plan
from .executor import execute, KERNEL_LOCK
from .validation import validate
from .manufacturing import manufacturing_record
from .cad_io import CadExportError

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Project:
    analysis: object
    requirements: Requirements
    id: str = field(default_factory=lambda: uuid4().hex)
    stage: str = "analyzed"
    revisions: list = field(default_factory=list)
    active_id: str | None = None
    messages: list = field(default_factory=list)
    error: str | None = None
    highlights: tuple = ()
    feedback: list = field(default_factory=list)
    last_attempt: BuildFeedback | None = None
    last_planner_attempt: dict | None = None
    _analysis_json: tuple = field(default=(), init=False, repr=False, compare=False)
    _revision_json: dict = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    @classmethod
    def new(cls, analysis):
        return cls(
            analysis,
            Requirements(
                interface_id=recommended_interface(analysis),
                manufacturing_features=True,
                defer_passages=True,
            ),
        )

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        if not path.is_relative_to((ROOT / "artifacts").resolve()):
            raise ValueError("Project must be in local artifacts.")
        data = json.loads(path.read_text(encoding="utf-8"))
        obj = cls(
            Analysis.model_validate(data["analysis"]),
            Requirements.model_validate(data["requirements"]),
            id=path.parent.name,
        )
        for entry in data["revisions"]:
            rev = Revision.model_validate(entry)
            artifact = Path(rev.artifact).resolve()
            if not artifact.is_relative_to(path.parent) or not artifact.is_file():
                raise ValueError(
                    "Project CAD artifact missing or outside project directory."
                )
            obj.revisions.append(rev)
        obj.active_id = data["active_id"]
        obj.messages = data["messages"]
        obj.feedback = [
            FeedbackRecord.model_validate(x) for x in data.get("feedback", [])
        ]
        obj.last_planner_attempt = data.get("last_planner_attempt")
        obj.stage = "presented" if obj.current else "analyzed"
        if data.get("stage") in ("clarifying", "proposing", "presented", "exported"):
            obj.stage = data["stage"]
        elif not obj.current and (
            (obj.last_planner_attempt or {}).get("action") or {}
        ).get("questions"):
            # Legacy snapshots did not save stage. With existing CAD, retain
            # their review state rather than replaying a pre-build question.
            obj.stage = "clarifying"
        return obj

    @property
    def current(self):
        return next((r for r in self.revisions if r.id == self.active_id), None)

    def generate(
        self, requirements=None, change="Generate design", progress=lambda s: None
    ):
        candidate = requirements or self.requirements
        old = self.current
        self.last_attempt = BuildFeedback(requirements=candidate)
        try:
            for key in self.requirements.locks:
                if getattr(candidate, key) != getattr(self.requirements, key):
                    raise ValueError(
                        f"{key} is locked; unlock it explicitly before changing it."
                    )
            self.stage = "revising" if old else "generating"
            progress("Planning the fixture")
            plan = compile_plan(self.analysis, candidate)
            self.last_attempt = self.last_attempt.model_copy(update={"plan": plan})
            rid = uuid4().hex[:12]
            folder = ROOT / "artifacts" / self.id / rid
            folder.mkdir(parents=True)
            progress("Building geometry in SMLib")
            with KERNEL_LOCK:
                bodies, meshes, cuts = execute(
                    plan, self.analysis, folder / "fixture.usda"
                )
                self.stage = "checking"
                progress("Checking geometry and export")
                checks = validate(self.analysis, candidate, plan, bodies, cuts)
                self.last_attempt = self.last_attempt.model_copy(
                    update={"checks": checks}
                )
                failures = [c for c in checks if c.result == "failed"]
                if failures:
                    raise ValueError(
                        "; ".join(
                            c.name + ": " + str(c.measured) + ". " + c.correction
                            for c in failures
                        )
                    )
                metrics = {
                    "volume_mm3": sum(b.volume() for b in bodies.values()),
                    "body_count": float(len(bodies)),
                    "hole_count": float(len(cuts)),
                    "base_hole_count": float(
                        sum(
                            op.purpose == "Surrounding attachment bolt clearance"
                            for op in plan.operations
                        )
                    ),
                    "fixture_opening_count": float(len(candidate.fixture_openings)),
                }
            summary = f"Built {len(bodies)} fixture solid(s) for {len(plan.placements)} part(s): {len(cuts)} part holes, {int(metrics['base_hole_count'])} base holes."
            revision = Revision(
                id=rid,
                parent=self.active_id,
                changes=change,
                requirements=candidate,
                plan=plan,
                artifact=str(folder / "fixture.usda"),
                meshes=meshes,
                checks=checks,
                metrics=metrics,
                summary=summary,
            )
            (folder / "revision.json").write_text(
                revision.model_dump_json(indent=2), encoding="utf-8"
            )
            (folder / "analysis.json").write_text(
                self.analysis.model_dump_json(indent=2), encoding="utf-8"
            )
            self.revisions.append(revision)
            self.active_id = rid
            self.last_attempt = self.last_attempt.model_copy(
                update={"revision_id": rid, "metrics": metrics}
            )
            self.requirements = candidate
            self.error = None
            self.stage = "presented"
            self.save()
            return revision
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            self.last_attempt = self.last_attempt.model_copy(
                update={
                    "error": self.error,
                    "failure_kind": "cad_export"
                    if isinstance(error, CadExportError)
                    else "design",
                }
            )
            self.stage = "presented" if old else "proposing"
            raise

    def restore(self, rid):
        revision = next(r for r in self.revisions if r.id == rid)
        self.active_id = rid
        self.requirements = revision.requirements
        self.stage = "presented"
        self.error = None
        self.save()

    def save(self):
        folder = ROOT / "artifacts" / self.id
        folder.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "version": 1,
            "stage": self.stage,
            "requirements": self.requirements.model_dump(),
            "active_id": self.active_id,
            "messages": self.messages,
            "feedback": [f.model_dump() for f in self.feedback],
            "last_planner_attempt": self.last_planner_attempt,
        }
        temp = folder / "project.tmp"
        # Immutable geometry dominates large projects. Serialize it once and
        # reuse those exact bytes for selection-only saves, without changing the
        # on-disk schema or the atomic replacement/rollback contract.
        if not self._analysis_json or self._analysis_json[0] is not self.analysis:
            self._analysis_json = (self.analysis, self.analysis.model_dump_json())
        revisions = {}
        for revision in self.revisions:
            cached = self._revision_json.get(revision.id)
            revisions[revision.id] = (
                cached
                if cached and cached[0] is revision
                else (revision, revision.model_dump_json())
            )
        self._revision_json = revisions
        payload = (
            json.dumps(snapshot)[:-1]
            + ',"analysis":'
            + self._analysis_json[1]
            + ',"revisions":['
            + ",".join(v[1] for v in revisions.values())
            + "]}"
        )
        temp.write_text(payload, encoding="utf-8")
        temp.replace(folder / "project.json")

    def export(self, mark_exported=True):
        r = self.current
        if not r:
            raise ValueError("Generate a valid revision before export.")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(r.artifact, "fixture.usda")
            from .step_export import prepared_step

            step_file = prepared_step(r)
            step_report = Path(r.artifact).with_name("step-export.json")
            if step_file:
                z.write(step_file, "fixture.step")
                z.write(step_report, "step-export.json")
            review_image = Path(r.artifact).with_name("review.png")
            if review_image.is_file():
                z.write(review_image, "review.png")
            z.writestr("revision.json", r.model_dump_json(indent=2))
            z.writestr("plan.json", r.plan.model_dump_json(indent=2))
            z.writestr(
                "fastener-clearances.json",
                json.dumps([c.model_dump() for c in r.plan.clearances], indent=2),
            )
            z.writestr("requirements.json", r.requirements.model_dump_json(indent=2))
            if r.plan.sheet_panels:
                from .sheet_metal import manufacturing_record as sheet_record

                z.writestr(
                    "sheet-metal.json",
                    json.dumps(sheet_record(r.requirements, r.plan), indent=2),
                )
            if r.plan.version >= 9:
                from .hardware import hardware_record

                z.writestr(
                    "hardware.json",
                    json.dumps(
                        hardware_record(self.analysis, r.requirements, r.plan), indent=2
                    ),
                )
            if r.requirements.base_mount:
                z.writestr(
                    "base-analysis.json",
                    r.requirements.base_mount.analysis.model_dump_json(indent=2),
                )
            # Each export describes this revision's review, never a newer attempt.
            z.writestr(
                "ai-feedback.json",
                json.dumps(
                    [
                        f.model_dump()
                        for f in self.feedback
                        if f.build.revision_id == r.id
                    ],
                    indent=2,
                ),
            )
            z.writestr(
                "manufacturing.json",
                json.dumps(manufacturing_record(r.requirements), indent=2),
            )
            z.writestr(
                "validation.json",
                json.dumps([c.model_dump() for c in r.checks], indent=2),
            )
            z.writestr("source-analysis.json", self.analysis.model_dump_json(indent=2))
            z.writestr(
                "README.txt",
                "Fixture geometry is real SMLib USD BRep in millimeters. If STEP was prepared, fixture.step contains the generated fixture solids and step-export.json records native/STEP verification. Source parts are not included in either CAD format. Source meshes are previews only. Supply the original STEP with matching SHA256 for re-analysis. Reproduction: python scripts/reproduce.py <this.zip> <output-folder>. No physical performance certification.\n",
            )
        if mark_exported:
            self.stage = "exported"
        return output.getvalue()
