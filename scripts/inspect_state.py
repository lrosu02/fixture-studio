"""Read a saved project's workflow and export readiness as JSON; never build or save."""

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fixture.lifecycle import workflow_state
from fixture.project import Project
from fixture.step_export import prepared_step


def describe_project(path):
    project = Project.load(path)
    current = project.current
    return {
        "schema_version": 1,
        "project_id": project.id,
        "workflow": workflow_state(project).model_dump(mode="json"),
        "changed_requirement_fields": [
            name
            for name in type(project.requirements).model_fields
            if current
            and getattr(project.requirements, name)
            != getattr(current.requirements, name)
        ],
        "step": (
            "unavailable"
            if current is None
            else "verified"
            if prepared_step(current)
            else "not_prepared_or_invalid"
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="Local artifacts/<id>/project.json")
    args = parser.parse_args()
    try:
        result = describe_project(args.project)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Cannot inspect project: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
