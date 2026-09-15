"""Golden-file helpers for quant tests (spec v4 §17).

Golden JSON lives under ``apps/api/tests/golden/quant/``. Values are compared with
a numeric tolerance; the model/config versions are kept inside each golden file.
Regenerate deliberately with ``UPDATE_GOLDEN=1 pytest ...`` after reviewing the
diff — never silently.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden" / "quant"
DEFAULT_TOL = 1e-8


def _diff(path: str, a, b, tol: float) -> list[str]:
    """Recursively compare, returning human-readable mismatch lines (empty = equal)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}.{k}: missing in actual")
            elif k not in b:
                out.append(f"{path}.{k}: unexpected in actual")
            else:
                out += _diff(f"{path}.{k}", a[k], b[k], tol)
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: length {len(b)} != expected {len(a)}"]
        out = []
        for i, (x, y) in enumerate(zip(a, b, strict=False)):
            out += _diff(f"{path}[{i}]", x, y, tol)
        return out
    if isinstance(a, (int | float)) and isinstance(b, (int | float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        return [] if abs(float(a) - float(b)) <= tol else \
            [f"{path}: {b} != expected {a} (tol {tol})"]
    return [] if a == b else [f"{path}: {b!r} != expected {a!r}"]


def assert_golden(name: str, actual: dict, tol: float = DEFAULT_TOL) -> None:
    """Compare ``actual`` against the named golden file, or (re)write it when
    UPDATE_GOLDEN=1 or the file is missing."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_DIR / f"{name}.json"
    if os.environ.get("UPDATE_GOLDEN") == "1" or not path.exists():
        path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
        return
    expected = json.loads(path.read_text())
    diffs = _diff(name, expected, actual, tol)
    assert not diffs, "Golden mismatch for {}:\n{}".format(name, "\n".join(diffs))
