#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


Json = dict[str, Any]


def load_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"{path}: empty file")
    return json.loads(text)


def type_names(value: Any) -> set[str]:
    if value is None:
        return {"null"}
    if isinstance(value, bool):
        return {"boolean"}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"integer", "number"}
    if isinstance(value, float):
        return {"number"}
    if isinstance(value, str):
        return {"string"}
    if isinstance(value, list):
        return {"array"}
    if isinstance(value, dict):
        return {"object"}
    return {type(value).__name__}


def expected_types(spec: Json) -> set[str]:
    raw = spec.get("type")
    if isinstance(raw, list):
        return set(raw)
    if isinstance(raw, str):
        return {raw}
    return set()


def validate(value: Any, spec: Json, path: str = "$") -> list[str]:
    errors: list[str] = []
    types = expected_types(spec)
    if types and type_names(value).isdisjoint(types):
        errors.append(f"{path}: expected {sorted(types)}, got {sorted(type_names(value))}")
        return errors

    if "enum" in spec and value not in spec["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {spec['enum']!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in spec and value < spec["minimum"]:
            errors.append(f"{path}: {value} < minimum {spec['minimum']}")
        if "maximum" in spec and value > spec["maximum"]:
            errors.append(f"{path}: {value} > maximum {spec['maximum']}")

    if isinstance(value, dict):
        for key in spec.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required key {key!r}")
        props = spec.get("properties") or {}
        for key, child_spec in props.items():
            if key in value:
                errors.extend(validate(value[key], child_spec, f"{path}.{key}"))

    if isinstance(value, list) and "items" in spec:
        for idx, item in enumerate(value):
            errors.extend(validate(item, spec["items"], f"{path}[{idx}]"))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate runtime JSON against a lightweight JSON schema subset.")
    parser.add_argument("--schema", required=True)
    parser.add_argument("json_file", nargs="+")
    args = parser.parse_args()

    schema = load_json(Path(args.schema))
    failed = False
    for json_name in args.json_file:
        try:
            payload = load_json(Path(json_name))
            errors = validate(payload, schema)
        except Exception as exc:
            errors = [str(exc)]
        if errors:
            failed = True
            print(f"FAIL {json_name}")
            for err in errors:
                print(f"  {err}")
        else:
            print(f"OK {json_name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
