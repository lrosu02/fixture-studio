from pathlib import Path
import tempfile

# Keep test scratch data inside the local workspace on restricted Windows hosts.
scratch = Path(__file__).resolve().parents[1] / "artifacts" / "test-temp"
scratch.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(scratch)
