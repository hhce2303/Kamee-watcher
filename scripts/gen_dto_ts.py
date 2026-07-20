"""Generate a combined JSON Schema from project/app/core/api/dto.py (ADR-0009).

Part of the DTO/type-sync strategy: this is the Python half of a two-step
codegen — `npm run gen:dto` runs this script, then pipes the schema through
`json-schema-to-typescript` to produce `src/types/dto.gen.ts`. Keeping the
schema step in Python (not a hand-maintained TS mirror) means the frontend
types cannot drift from the Pydantic models that define the wire contract.

Usage: python scripts/gen_dto_ts.py [output_path]
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "project"))

from pydantic import BaseModel  # noqa: E402
from pydantic.json_schema import models_json_schema  # noqa: E402

from app.core.api import dto  # noqa: E402


def _collect_models() -> list[type[BaseModel]]:
    """Every BaseModel subclass defined directly in dto.py, in source order."""
    models = [
        obj
        for name, obj in vars(dto).items()
        if inspect.isclass(obj)
        and issubclass(obj, BaseModel)
        and obj.__module__ == dto.__name__
        and not name.startswith("_")  # skip internal bases (e.g. _Command)
    ]
    # models_json_schema errors on duplicate refs if a class appears twice —
    # vars() already de-dupes by name, but sort for a stable, reviewable diff.
    return sorted(models, key=lambda m: m.__name__)


def _strip_titles(node: object) -> object:
    """Recursively drop 'title' keys.

    Pydantic stamps a per-field title (e.g. "Duration S") on every property by
    default; json-schema-to-typescript hoists any titled sub-schema into its
    own named type alias, which turns each DTO into a wall of noise types
    (DurationS, DurationS1, Path2, ...). The $defs key already names each
    model, so field-level titles serve no purpose here.
    """
    if isinstance(node, dict):
        return {k: _strip_titles(v) for k, v in node.items() if k != "title"}
    if isinstance(node, list):
        return [_strip_titles(v) for v in node]
    return node


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "src" / "types" / "dto.schema.json"
    models = _collect_models()
    _, top_level_schema = models_json_schema(
        [(m, "validation") for m in models],
        title="TheWatcherDto",
    )
    top_level_schema = _strip_titles(top_level_schema)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(top_level_schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(models)} DTO schemas to {output}")


if __name__ == "__main__":
    main()
