"""Package source and permitted demo artifacts; exclude local environments/data."""

from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "FixtureStudio-submission.zip"
    files = [
        ROOT / name
        for name in (
            "app.py",
            "README.md",
            "CHANGELOG.md",
            "STATE_MACHINES.md",
            "Notes.md",
            "IMPLEMENTATION_PLAN.md",
            "requirements.lock",
            ".gitignore",
            ".gitattributes",
            "FixtureStudio-demo.mp4",
        )
    ]
    for folder in ("fixture", "scripts", "tests", "samples", "demo", ".streamlit"):
        files.extend(
            p
            for p in (ROOT / folder).rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.name not in ("secrets.toml", ".env")
            and not p.name.endswith(".log")
        )
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(files):
            z.write(path, path.relative_to(ROOT).as_posix())
    print(f"{output.name}: {len(files)} files, {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
