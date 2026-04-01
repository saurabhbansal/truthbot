from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / "venv" / "bin" / "python"


def run(cmd: list[str]) -> None:
    print(f"\n> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    if not PY.exists():
        print("Missing virtualenv python at:", PY)
        return 2

    run([str(PY), "-m", "compileall", "app"])
    run([str(PY), "tests/claim_parser_local_validation.py"])
    run([str(PY), "tests/local_smoke_offline.py"])
    print("\nLocal predeploy gate check PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
