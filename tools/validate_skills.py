#!/usr/bin/env python3
"""Tier 1 validator: skill metadata plus optional full Draft 2020-12 JSON Schema validation."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent.parent
if str(KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(KIT_ROOT))

from shared.target_loader import validate_target_dict  # noqa: E402

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_LINES = 500
MAX_WORDS_APPROX_5K_TOKENS = 3800


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("Missing opening '---' YAML frontmatter delimiter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("Missing closing '---' YAML frontmatter delimiter")
    raw_fm = text[4:end]
    body = text[end + 5:]
    meta: dict[str, str] = {}
    for line in raw_fm.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


def validate_skill_md(skill_md: Path) -> list[str]:
    errors: list[str] = []
    text = skill_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        errors.append(f"{skill_md}: {len(lines)} lines exceeds {MAX_LINES}-line progressive disclosure limit")

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
        errors.append(f"{skill_md}: invalid name '{name}' (must be lowercase alphanumeric/hyphens, <=64 chars)")
    elif name != folder:
        errors.append(f"{skill_md}: name '{name}' must match parent directory '{folder}'")

    if not desc:
        errors.append(f"{skill_md}: missing required 'description' field")
    elif len(desc) > 1024:
        errors.append(f"{skill_md}: description length {len(desc)} exceeds 1024 chars")

    word_count = len(body.split())
    if word_count > MAX_WORDS_APPROX_5K_TOKENS:
        errors.append(f"{skill_md}: body ~{word_count} words exceeds ~5,000-token budget")
    return errors


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_json_instance(instance: dict, schema: dict, label: str, require_jsonschema: bool = False) -> list[str]:
    """Validate with jsonschema when available; runtime remains dependency-free."""
    try:
        import jsonschema
    except ImportError:
        if require_jsonschema:
            return [f"{label}: jsonschema is required for strict schema validation"]
        return []

    errors: list[str] = []
    try:
        validator_cls = jsonschema.validators.validator_for(schema)
        validator_cls.check_schema(schema)
        validator = validator_cls(schema)
        for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
            where = ".".join(map(str, err.path)) or "<root>"
            errors.append(f"{label}: schema violation at {where}: {err.message}")
    except Exception as exc:  # schema errors should fail validation, not crash CI
        errors.append(f"{label}: schema validation failed: {exc}")
    return errors


def validate_repo(kit_root: Path | None = None, require_jsonschema: bool | None = None) -> list[str]:
    root = (kit_root or KIT_ROOT).resolve()
    strict = (
        os.environ.get("BLENDER_AGENT_KIT_STRICT_SCHEMA") == "1"
        if require_jsonschema is None
        else require_jsonschema
    )
    errors: list[str] = []

    skill_files = sorted(root.glob("skills/**/SKILL.md")) + sorted(root.glob("plugins/**/SKILL.md"))
    if not skill_files:
        errors.append("No SKILL.md files found under skills/ or plugins/")
    for smd in skill_files:
        errors.extend(validate_skill_md(smd))

    schema_paths = {
        "target": root / "schemas" / "target.schema.json",
        "asset-manifest": root / "schemas" / "asset-manifest.schema.json",
    }
    schemas: dict[str, dict] = {}
    for name, sp in schema_paths.items():
        if not sp.is_file():
            errors.append(f"Missing required schema file: {sp.relative_to(root)}")
            continue
        try:
            schemas[name] = _load_json(sp)
            errors.extend(validate_json_instance({}, schemas[name], f"{name} schema", require_jsonschema=strict)[:0])
            # check_schema happens during real instance validation below; parsing here still catches malformed JSON.
        except Exception as exc:
            errors.append(f"{sp}: failed to parse schema JSON: {exc}")

    for tjson in sorted(root.glob("plugins/targets/*/target.json")):
        data = _load_json(tjson)
        for err in validate_target_dict(data, folder_name=tjson.parent.name):
            errors.append(f"{tjson}: {err}")
        if "target" in schemas:
            errors.extend(
                validate_json_instance(data, schemas["target"], str(tjson), require_jsonschema=strict)
            )

    # Validate committed example/manifests if project packs add any later.
    if "asset-manifest" in schemas:
        for manifest in sorted(root.glob("**/*.asset.manifest.json")):
            errors.extend(
                validate_json_instance(
                    _load_json(manifest),
                    schemas["asset-manifest"],
                    str(manifest),
                    require_jsonschema=strict,
                )
            )
    return errors


def main() -> int:
    errs = validate_repo()
    if errs:
        print("VALIDATION FAILED:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("ALL SKILL SPECS, TARGETS, AND AVAILABLE JSON-SCHEMA CHECKS VALID.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
