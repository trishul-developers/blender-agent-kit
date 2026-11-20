"""Bounded folder-scale Blender Agent Kit orchestration with safe cache evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from shared import deliver
from shared.profile_loader import load_profiled_target
from shared.runner import find_blender, run_blender_module
from shared.version import KIT_VERSION

CACHE_SCHEMA_VERSION = "1.0"
DEFAULT_MAX_ASSETS = 100


def _json_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _hash_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    unique = sorted({Path(p).resolve() for p in paths}, key=lambda p: p.as_posix())
    for path in unique:
        if not path.is_file():
            continue
        h.update(b"file\0")
        h.update(path.name.encode("utf-8"))
        h.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


def _tool_identity(root: Path) -> str:
    """Hash executable/config truth so code or policy changes invalidate cache."""
    candidates: list[Path] = []
    for pattern in (
        "shared/**/*.py",
        "tools/*.py",
        "skills/core/blender-core/scripts/run.py",
        "plugins/targets/*/target.json",
        "plugins/policies/*/policy.json",
        "schemas/*.json",
    ):
        candidates.extend(root.glob(pattern))
    h = hashlib.sha256()
    h.update(KIT_VERSION.encode("utf-8"))
    for path in sorted({p.resolve() for p in candidates if p.is_file()}, key=lambda p: p.as_posix()):
        rel = path.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


def _blender_identity(explicit: str | None) -> dict:
    exe = Path(find_blender(explicit)).resolve()
    proc = subprocess.run(
        [str(exe), "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
    )
    first_line = next((line.strip() for line in proc.stdout.splitlines() if line.strip()), "")
    if proc.returncode != 0 or not first_line:
        raise RuntimeError(f"Unable to identify Blender executable {exe}: {proc.stdout[-1000:]}")
    stat = exe.stat()
    return {
        "path": str(exe),
        "version": first_line,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _resolved_config_identity(
    target: str,
    texture_profile: str | None,
    project_profile: str | None,
) -> dict:
    cfg, chosen, _target_dir, project_data, _project_path = load_profiled_target(
        target,
        texture_profile=texture_profile,
        project_profile=project_profile,
    )
    return {
        "target": cfg,
        "texture_profile": chosen,
        "project_profile": project_data,
    }


def _item_key(path: Path, input_root: Path) -> str:
    rel = path.resolve().relative_to(input_root.resolve())
    if path.is_file():
        rel = rel.with_suffix("")
    parts = [part for part in rel.parts if part not in ("", ".")]
    return "__".join(parts) or path.stem or path.name


def _discover_blends(root: Path, pattern: str, recursive: bool) -> list[Path]:
    iterator = root.rglob(pattern) if recursive else root.glob(pattern)
    return sorted((p.resolve() for p in iterator if p.is_file() and p.suffix.lower() == ".blend"), key=lambda p: p.as_posix())


def _discover_pack_dirs(root: Path, pattern: str, recursive: bool) -> list[Path]:
    iterator = root.rglob(pattern) if recursive else root.glob(pattern)
    return sorted(
        (
            p.resolve()
            for p in iterator
            if p.is_dir() and any(child.is_file() and child.suffix.lower() == ".png" for child in p.iterdir())
        ),
        key=lambda p: p.as_posix(),
    )


def _bundle_spec(source: Path, template: str | None) -> Path:
    name = template or "{stem}.bundle.json"
    rendered = name.format(stem=source.stem, name=source.name)
    path = Path(rendered)
    if not path.is_absolute():
        path = source.parent / path
    return path.resolve()


def _source_inputs(
    operation: str,
    source: Path,
    bundle_spec_template: str | None,
) -> list[Path]:
    if operation == "pack":
        return sorted((p for p in source.iterdir() if p.is_file() and p.suffix.lower() == ".png"), key=lambda p: p.name)
    inputs = [source]
    if operation == "bundle" or (operation == "deliver" and bundle_spec_template):
        spec = _bundle_spec(source, bundle_spec_template)
        if spec.is_file():
            inputs.append(spec)
    return inputs


def _cache_key(
    *,
    source_inputs: list[Path],
    operation: str,
    tool_identity: str,
    blender_identity: dict,
    config_identity: dict,
    options: dict,
) -> str:
    h = hashlib.sha256()
    h.update(_hash_files(source_inputs).encode("ascii"))
    h.update(b"\0tool\0")
    h.update(tool_identity.encode("ascii"))
    h.update(b"\0metadata\0")
    h.update(_json_bytes({
        "cache_schema": CACHE_SCHEMA_VERSION,
        "kit_version": KIT_VERSION,
        "operation": operation,
        "blender": blender_identity,
        "config": config_identity,
        "options": options,
    }))
    return "sha256:" + h.hexdigest()


def _resolve_artifact_path(value: str, roots: list[Path]) -> Path | None:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    for root in roots:
        joined = (root / candidate).resolve()
        if joined.is_file():
            return joined
    return None


def _artifact_evidence(result: dict, roots: list[Path]) -> tuple[list[str], list[dict]]:
    """Collect generated artifacts and manifest/build-hash checks recursively."""
    artifacts: set[str] = set()
    manifest_checks: list[dict] = []

    def visit(value, under_artifacts: bool = False):
        if isinstance(value, dict):
            for key, item in value.items():
                now_artifacts = under_artifacts or key == "artifacts"
                if now_artifacts and isinstance(item, str):
                    resolved = _resolve_artifact_path(item, roots)
                    if resolved:
                        artifacts.add(str(resolved))
                        if key == "manifest" or resolved.name.endswith(".manifest.json"):
                            try:
                                data = json.loads(resolved.read_text(encoding="utf-8"))
                            except Exception:
                                data = {}
                            build_hash = data.get("build_hash")
                            required_files: list[str] = []
                            if isinstance(data.get("export_file"), str):
                                required_files.append(str((resolved.parent / data["export_file"]).resolve()))
                            for part in data.get("parts", []):
                                if isinstance(part, dict) and isinstance(part.get("file"), str):
                                    required_files.append(str((resolved.parent / part["file"]).resolve()))
                            manifest_checks.append({
                                "path": str(resolved),
                                "build_hash": build_hash,
                                "required_files": sorted(set(required_files)),
                            })
                else:
                    visit(item, now_artifacts)
        elif isinstance(value, list):
            for item in value:
                visit(item, under_artifacts)
        elif under_artifacts and isinstance(value, str):
            resolved = _resolve_artifact_path(value, roots)
            if resolved:
                artifacts.add(str(resolved))

    visit(result)
    return sorted(artifacts), manifest_checks


def _cache_record_valid(record: dict, expected_key: str) -> bool:
    if record.get("schema_version") != CACHE_SCHEMA_VERSION:
        return False
    if record.get("cache_key") != expected_key or record.get("status") != "ok":
        return False
    for artifact in record.get("artifacts", []):
        if not Path(artifact).is_file():
            return False
    for check in record.get("manifest_checks", []):
        path = Path(check.get("path", ""))
        if not path.is_file():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        expected_hash = check.get("build_hash")
        if expected_hash and data.get("build_hash") != expected_hash:
            return False
        if any(not Path(p).is_file() for p in check.get("required_files", [])):
            return False
    return True


def _write_cache(
    cache_file: Path,
    *,
    cache_key: str,
    operation: str,
    source: Path,
    result: dict,
    item_out: Path,
) -> dict:
    roots = [item_out, item_out / "packed", item_out / "export", item_out / "review", item_out / "delivery"]
    artifacts, manifest_checks = _artifact_evidence(result, roots)
    record = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "status": "ok",
        "operation": operation,
        "source": str(source),
        "cache_key": cache_key,
        "artifacts": artifacts,
        "manifest_checks": manifest_checks,
        "result": result,
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def _operation_success(operation: str, result: dict) -> bool:
    if result.get("status") != "ok":
        return False
    if operation == "qa":
        return bool(result.get("passed", False))
    return True


def _run_item(
    *,
    operation: str,
    source: Path,
    item_out: Path,
    blender_exe: str | None,
    addons: list[str] | None,
    target: str,
    texture_profile: str | None,
    project_profile: str | None,
    asset_class: str,
    material: str | None,
    pack_size: int | None,
    detect_normal_y: bool,
    bundle_spec_template: str | None,
    review_style: str,
    no_roundtrip: bool,
    timeout_sec: int,
    kit_root: Path,
) -> dict:
    item_out.mkdir(parents=True, exist_ok=True)

    if operation == "qa":
        args = ["--target", target, "--asset-class", asset_class]
        if project_profile:
            args += ["--project-profile", project_profile]
        return run_blender_module(
            "shared.qa_checks",
            module_args=args,
            blend_file=str(source),
            blender_exe=blender_exe,
            addons=addons,
            kit_root=kit_root,
            timeout_sec=timeout_sec,
        )

    if operation == "export":
        args = ["--target", target, "--out", str(item_out / "export"), "--asset-id", source.stem, "--category", asset_class]
        if texture_profile:
            args += ["--profile", texture_profile]
        if project_profile:
            args += ["--project-profile", project_profile]
        if no_roundtrip:
            args.append("--no-roundtrip")
        return run_blender_module(
            "shared.exporter",
            module_args=args,
            blend_file=str(source),
            blender_exe=blender_exe,
            addons=addons,
            kit_root=kit_root,
            timeout_sec=timeout_sec,
        )

    if operation == "bundle":
        spec = _bundle_spec(source, bundle_spec_template)
        if not spec.is_file():
            return {"status": "error", "error": f"Bundle spec not found: {spec}"}
        args = ["--spec", str(spec), "--target", target, "--out", str(item_out / "export")]
        if texture_profile:
            args += ["--profile", texture_profile]
        if project_profile:
            args += ["--project-profile", project_profile]
        if no_roundtrip:
            args.append("--no-roundtrip")
        return run_blender_module(
            "shared.bundle_exporter",
            module_args=args,
            blend_file=str(source),
            blender_exe=blender_exe,
            addons=addons,
            kit_root=kit_root,
            timeout_sec=timeout_sec,
        )

    if operation == "deliver":
        spec = None
        if bundle_spec_template:
            candidate = _bundle_spec(source, bundle_spec_template)
            if not candidate.is_file():
                return {"status": "error", "error": f"Bundle spec not found: {candidate}"}
            spec = str(candidate)
        return deliver.run(
            blend_file=str(source),
            target=target,
            asset_class=asset_class,
            texture_profile=texture_profile,
            project_profile=project_profile,
            out_dir=str(item_out / "delivery"),
            blender_exe=blender_exe,
            addons=addons,
            review_style=review_style,
            bundle_spec=spec,
            asset_id=source.stem,
            no_export=False,
            timeout_sec=timeout_sec,
            kit_root=kit_root,
        )

    if operation == "pack":
        if not material:
            return {"status": "error", "error": "--material is required for batch pack"}
        args = [
            "--target", target,
            "--asset-id", source.name,
            "--material", material,
            "--input-dir", str(source),
            "--out", str(item_out / "packed"),
        ]
        if texture_profile:
            args += ["--profile", texture_profile]
        if project_profile:
            args += ["--project-profile", project_profile]
        if pack_size is not None:
            args += ["--size", str(pack_size)]
        if detect_normal_y:
            args.append("--detect-normal-y")
        return run_blender_module(
            "shared.channel_pack",
            module_args=args,
            blender_exe=blender_exe,
            addons=addons,
            kit_root=kit_root,
            timeout_sec=timeout_sec,
        )

    raise ValueError(f"Unsupported batch operation: {operation}")


def run(
    *,
    operation: str,
    input_dir: str,
    out_dir: str = "batch-build",
    pattern: str | None = None,
    recursive: bool = False,
    max_assets: int = DEFAULT_MAX_ASSETS,
    target: str = "unity",
    texture_profile: str | None = None,
    project_profile: str | None = None,
    asset_class: str = "solid_prop",
    material: str | None = None,
    pack_size: int | None = None,
    detect_normal_y: bool = False,
    bundle_spec_template: str | None = None,
    review_style: str = "technical",
    no_roundtrip: bool = False,
    blender_exe: str | None = None,
    addons: list[str] | None = None,
    no_cache: bool = False,
    refresh_cache: bool = False,
    timeout_sec: int = 600,
    kit_root: Path | None = None,
) -> dict:
    root = (kit_root or Path(__file__).resolve().parents[1]).resolve()
    source_root = Path(input_dir).expanduser().resolve()
    output_root = Path(out_dir).expanduser().resolve()
    started = time.perf_counter()

    if operation not in {"qa", "pack", "export", "bundle", "deliver"}:
        return {"status": "error", "error": f"Unsupported operation: {operation}", "items": []}
    if not source_root.is_dir():
        return {"status": "error", "error": f"Input directory not found: {source_root}", "items": []}
    if max_assets < 1:
        return {"status": "error", "error": "--max-assets must be >= 1", "items": []}
    if operation == "pack" and not material:
        return {"status": "error", "error": "--material is required for batch pack", "items": []}

    chosen_pattern = pattern or ("*" if operation == "pack" else "*.blend")
    sources = (
        _discover_pack_dirs(source_root, chosen_pattern, recursive)
        if operation == "pack"
        else _discover_blends(source_root, chosen_pattern, recursive)
    )
    if not sources:
        return {
            "status": "error",
            "error": f"No batch inputs matched pattern '{chosen_pattern}' in {source_root}",
            "discovered": 0,
            "items": [],
        }
    if len(sources) > max_assets:
        return {
            "status": "error",
            "error": f"Discovered {len(sources)} assets, exceeding --max-assets {max_assets}",
            "discovered": len(sources),
            "items": [],
        }

    output_root.mkdir(parents=True, exist_ok=True)
    tool_id = _tool_identity(root)
    blender_id = _blender_identity(blender_exe)
    config_id = _resolved_config_identity(target, texture_profile, project_profile)
    effective_blender = blender_id["path"]

    option_identity = {
        "target": target,
        "texture_profile": texture_profile,
        "project_profile": project_profile,
        "asset_class": asset_class,
        "material": material,
        "pack_size": pack_size,
        "detect_normal_y": detect_normal_y,
        "bundle_spec_template": bundle_spec_template,
        "review_style": review_style,
        "no_roundtrip": no_roundtrip,
    }

    items: list[dict] = []
    processed = skipped = failed = 0

    for source in sources:
        item_started = time.perf_counter()
        key_name = _item_key(source, source_root)
        item_out = output_root / key_name
        cache_file = item_out / f".batch-cache.{operation}.json"
        source_inputs = _source_inputs(operation, source, bundle_spec_template)
        cache_key = _cache_key(
            source_inputs=source_inputs,
            operation=operation,
            tool_identity=tool_id,
            blender_identity=blender_id,
            config_identity=config_id,
            options=option_identity,
        )

        cache_record = None
        if not no_cache and not refresh_cache and cache_file.is_file():
            try:
                candidate = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                candidate = {}
            if _cache_record_valid(candidate, cache_key):
                cache_record = candidate

        if cache_record is not None:
            skipped += 1
            items.append({
                "source": str(source),
                "asset_id": source.name if source.is_dir() else source.stem,
                "status": "ok",
                "cache_hit": True,
                "cache_key": cache_key,
                "duration_ms": round((time.perf_counter() - item_started) * 1000.0, 3),
                "cache_file": str(cache_file),
                "result": cache_record.get("result", {}),
            })
            continue

        processed += 1
        result = _run_item(
            operation=operation,
            source=source,
            item_out=item_out,
            blender_exe=effective_blender,
            addons=addons,
            target=target,
            texture_profile=texture_profile,
            project_profile=project_profile,
            asset_class=asset_class,
            material=material,
            pack_size=pack_size,
            detect_normal_y=detect_normal_y,
            bundle_spec_template=bundle_spec_template,
            review_style=review_style,
            no_roundtrip=no_roundtrip,
            timeout_sec=timeout_sec,
            kit_root=root,
        )
        ok = _operation_success(operation, result)
        if not ok:
            failed += 1
        elif not no_cache:
            _write_cache(
                cache_file,
                cache_key=cache_key,
                operation=operation,
                source=source,
                result=result,
                item_out=item_out,
            )

        items.append({
            "source": str(source),
            "asset_id": source.name if source.is_dir() else source.stem,
            "status": "ok" if ok else "error",
            "cache_hit": False,
            "cache_key": cache_key,
            "duration_ms": round((time.perf_counter() - item_started) * 1000.0, 3),
            "cache_file": str(cache_file) if not no_cache else None,
            "result": result,
        })

    total_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return {
        "status": "ok" if failed == 0 else "error",
        "operation": operation,
        "input_dir": str(source_root),
        "out_dir": str(output_root),
        "pattern": chosen_pattern,
        "recursive": recursive,
        "tool_identity": tool_id,
        "blender_identity": blender_id,
        "cache": {
            "enabled": not no_cache,
            "refresh": refresh_cache,
            "hits": skipped,
            "misses": processed,
        },
        "counts": {
            "discovered": len(sources),
            "processed": processed,
            "skipped": skipped,
            "failed": failed,
        },
        "duration_ms": total_ms,
        "items": items,
        "telemetry": {
            "measured": ["duration_ms", "cache_hits", "cache_misses", "processed", "skipped", "failed"],
            "not_measured": ["model_tokens", "api_tokens", "agent_turns"],
        },
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser(description="Bounded folder-scale Blender Agent Kit batch processing.")
    p.add_argument("--operation", choices=["qa", "pack", "export", "bundle", "deliver"], required=True)
    p.add_argument("--input-dir", required=True)
    p.add_argument("--out", default="batch-build")
    p.add_argument("--pattern", default=None)
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--max-assets", type=int, default=DEFAULT_MAX_ASSETS)
    p.add_argument("--target", default="unity")
    p.add_argument("--profile", default=None)
    p.add_argument("--project-profile", default=None)
    p.add_argument("--asset-class", default="solid_prop")
    p.add_argument("--material", default=None)
    p.add_argument("--size", type=int, default=None)
    p.add_argument("--detect-normal-y", action="store_true")
    p.add_argument("--bundle-spec-template", default=None)
    p.add_argument("--review-style", default="technical")
    p.add_argument("--no-roundtrip", action="store_true")
    p.add_argument("--blender", default=None)
    p.add_argument("--addons", default=None)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--refresh-cache", action="store_true")
    p.add_argument("--timeout-sec", type=int, default=600)
    ns = p.parse_args(argv)
    addons = [v.strip() for v in ns.addons.split(",") if v.strip()] if ns.addons else None
    return run(
        operation=ns.operation,
        input_dir=ns.input_dir,
        out_dir=ns.out,
        pattern=ns.pattern,
        recursive=ns.recursive,
        max_assets=ns.max_assets,
        target=ns.target,
        texture_profile=ns.profile,
        project_profile=ns.project_profile,
        asset_class=ns.asset_class,
        material=ns.material,
        pack_size=ns.size,
        detect_normal_y=ns.detect_normal_y,
        bundle_spec_template=ns.bundle_spec_template,
        review_style=ns.review_style,
        no_roundtrip=ns.no_roundtrip,
        blender_exe=ns.blender,
        addons=addons,
        no_cache=ns.no_cache,
        refresh_cache=ns.refresh_cache,
        timeout_sec=ns.timeout_sec,
    )
