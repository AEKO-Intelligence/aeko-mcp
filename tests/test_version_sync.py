"""Keep package and MCP registry manifest versions synchronized."""

import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _field_value(payload, dotted_field):
    value = payload
    for part in dotted_field.split("."):
        value = value[part]
    return value


def test_configured_version_declarations_are_real_and_synchronized():
    config = json.loads((ROOT / ".version-bump.json").read_text())
    declarations = {}

    for entry in config["files"]:
        path = ROOT / entry["path"]
        assert path.is_file(), f"Configured version file does not exist: {path}"
        if path.suffix == ".toml":
            payload = tomllib.loads(path.read_text())
        elif path.suffix == ".json":
            payload = json.loads(path.read_text())
        else:  # pragma: no cover - protects future config edits
            raise AssertionError(f"Unsupported version declaration: {path}")
        declarations[entry["path"]] = str(
            _field_value(payload, entry["field"])
        )

    assert set(declarations) == {"pyproject.toml", "server.json"}
    assert len(set(declarations.values())) == 1, declarations
