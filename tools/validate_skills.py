#!/usr/bin/env python3
"""Tier 1 validator for skill metadata, targets, project profiles, and JSON Schemas."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent.parent
if str(KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(KIT_ROOT))

from shared.profile_loader import load_project_profile, validate_project_profile_dict  # noqa: E402
from shared.target_loader import load_target, validate_target_dict  # noqa: E402

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_LINES = 500
MAX_WORDS_APPROX_5K_TOKENS = 3800


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("Missing opening '---' YAML frontmatter delimiter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("Missing closing '---' YAML frontmatter delimiter")
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, text[end + 5:]


def validate_skill_md(skill_md: Path) -> list[str]:
    errors: list[str] = []
    text = skill_md.read_text(encoding="utf-8")
    if len(text.splitlines()) > MAX_LINES:
        errors.append(f"{skill_md}: exceeds {MAX_LINES}-line progressive disclosure limit")
    try:
        meta, body = parse_frontmatter(text)
    except ValueError as exc:
        return [f"{skill_md}: {exc}"]

    name = meta.get("name", "")
    desc = meta.get("description", "")
    folder = skill_md.parent.name
    if not name:
        errors.append(f"{skill_md}: missing required 'name' field")
    elif not NAME_RE.match(name) or len(name) > 64:
        errors.append(f"{skill_md}: invalid name '{name}'")
    elif name != folder:
        errors.append(f"{skill_md}: name '{name}' must match parent directory '{folder}'")
    if not desc:
        errors.append(f"{skill_md}: missing required 'description' field")
    elif len(desc) > 1024:
        errors.append(f"{skill_md}: description exceeds 1024 chars")
    if len(body.split()) > MAX_WORDS_APPROX_5K_TOKENS:
        errors.append(f"{skill_md}: body exceeds approximate 5,000-token budget")
    return errors


def _jsonschema_module(require: bool):
    try:
        import jsonschema
        return jsonschema
    except ImportError:
        if require:
            raise RuntimeError("jsonschema is required for strict schema validation")
        return None


def validate_schema_document(schema: dict, label: str, require_jsonschema: bool = False) -> list[str]:
    try:
        jsonschema = _jsonschema_module(require_jsonschema)
    except RuntimeError as exc:
        return [f"{label}: {exc}"]
    if jsonschema is None:
        return []
    try:
        cls = jsonschema.validators.validator_for(schema)
        cls.check_schema(schema)
        return []
    except Exception as exc:
        return [f"{label}: invalid JSON Schema: {exc}"]


def validate_json_instance(instance: dict, schema: dict, label: str, require_jsonschema: bool = False) -> list[str]:
    errors = validate_schema_document(schema, label, require_jsonschema=require_jsonschema)
    if errors:
        return errors
    jsonschema = _jsonschema_module(False)
    if jsonschema is None:
        return []
    validator = jsonschema.validators.validator_for(schema)(schema)
    result = []
    for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
        where = ".".join(map(str, err.path)) or "<root>"
        result.append(f"{label}: schema violation at {where}: {err.message}")
    return result


def validate_repo(kit_root: Path | None = None, require_jsonschema: bool | None = None) -> list[str]:
    root = (kit_root or KIT_ROOT).resolve()
    strict = (
        os.environ.get("BLENDER_AGENT_KIT_STRICT_SCHEMA") == "1"
        if require_jsonschema is None else require_jsonschema
    )
    errors: list[str] = []

    skill_files = sorted(root.glob("skills/**/SKILL.md")) + sorted(root.glob("plugins/**/SKILL.md"))
    if not skill_files:
        errors.append("No SKILL.md files found under skills/ or plugins/")
    for skill in skill_files:
        errors.extend(validate_skill_md(skill))

    schemas: dict[str, dict] = {}
    for sp in sorted((root / "schemas").glob("*.schema.json")):
        try:
            schema = json.loads(sp.read_text(encoding="utf-8"))
            schemas[sp.name] = schema
            errors.extend(validate_schema_document(schema, str(sp), require_jsonschema=strict))
        except Exception as exc:
            errors.append(f"{sp}: failed to parse schema JSON: {exc}")

    target_schema = schemas.get("target.schema.json")
    for tjson in sorted(root.glob("plugins/targets/*/target.json")):
        data = json.loads(tjson.read_text(encoding="utf-8"))
        errors.extend(f"{tjson}: {e}" for e in validate_target_dict(data, folder_name=tjson.parent.name))
        if target_schema:
            errors.extend(validate_json_instance(data, target_schema, str(tjson), require_jsonschema=strict))

    profile_schema = schemas.get("project-profile.schema.json")
    for pjson in sorted(root.glob("plugins/profiles/*/profile.json")):
        data = json.loads(pjson.read_text(encoding="utf-8"))
        errors.extend(f"{pjson}: {e}" for e in validate_project_profile_dict(data))
        if profile_schema:
            errors.extend(validate_json_instance(data, profile_schema, str(pjson), require_jsonschema=strict))
        for target_name, overlay in data.get("target_overrides", {}).items():
            try:
                load_target(target_name, kit_root=root, overlay=overlay)
            except Exception as exc:
                errors.append(f"{pjson}: target override '{target_name}' does not produce a valid target: {exc}")

    asset_manifest_schema = schemas.get("asset-manifest.schema.json")
    if asset_manifest_schema:
        for manifest in sorted(root.glob("**/*.asset.manifest.json")):
            errors.extend(validate_json_instance(
                json.loads(manifest.read_text(encoding="utf-8")),
                asset_manifest_schema, str(manifest), require_jsonschema=strict
            ))
    return errors


def main() -> int:
    errs = validate_repo()
    if errs:
        print("VALIDATION FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("ALL SKILLS, TARGETS, PROJECT PROFILES, AND JSON SCHEMAS VALID.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
