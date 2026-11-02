"""Isolated SMLib serialization worker; no design generation or repair."""

from pathlib import Path
import sys

import usd_brep as sm


def main(folder, count):
    directory = Path(folder).resolve()
    if not 1 <= count <= 64:
        raise ValueError("Native export body count is outside the supported limit.")
    bodies = [
        sm.Brep.read_from_file(str(directory / f"body-{n}.brep"), ascii=False)
        for n in range(count)
    ]
    sm.usd.export_breps(bodies, str(directory / "native.usda"))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
