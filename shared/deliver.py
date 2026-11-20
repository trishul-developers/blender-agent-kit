"""QA-gated host orchestration for a source-ready Blender asset."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from shared.paths import resolve_kit_root
from shared.runner import run_blender_module


def _append(args: list[str], flag: str, value) -> None:
    if value is not None:
        args.extend([flag, str(value)])


def _stage(
    name: str,
    module: str,
    module_args: list[str],
    *,
    blend_file: str | None,
    blender_exe: str | None,
    addons: list[str] | None,
    kit_root: Path,
    timeout_sec: int,
) -> dict:
    started = time.perf_counter()
    result = run_blender_module(
        module,
        module_args=module_args,
        blend_file=blend_file,
        addons=addons,
        blender_exe=blender_exe,
        kit_root=kit_root,
        timeout_sec=timeout_sec,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return {
        "name": name,
        "status": "ok" if result.get("status") == "ok" else "error",
        "duration_ms": elapsed_ms,
        "result": result,
    }


def run(
    *,
    blend_file: str,
    target: str = "unity",
    asset_class: str = "solid_prop",
    texture_profile: str | None = None,
    project_profile: str | None = None,
    out_dir: str = "delivery",
    blender_exe: str | None = None,
    addons: list[str] | None = None,
    device: str = "auto",
    review_style: str = "technical",
    review_preset: str | None = None,
    reference_fbx: str | None = None,
    bundle_spec: str | None = None,
    asset_id: str | None = None,
    export_category: str | None = None,
    rig_type: str = "none",
    uv1_source: str = "blender",
    pack_input_dir: str | None = None,
    material: str | None = None,
    pack_size: int | None = None,
    detect_normal_y: bool = False,
    no_review: bool = False,
    no_export: bool = False,
    continue_on_qa_error: bool = False,
    timeout_sec: int = 600,
    kit_root: Path | None = None,
) -> dict:
    root = (kit_root or resolve_kit_root()).resolve()
    blend = Path(blend_file).expanduser().resolve()
    if not blend.is_file():
        return {
            "status": "error",
            "failed_stage": "preflight",
            "error": f"Blend file not found: {blend}",
            "stages": [],
        }

    output = Path(out_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    stages: list[dict] = []
    total_started = time.perf_counter()

    common = ["--target", target]
    if project_profile:
        common += ["--project-profile", project_profile]

    inspect_stage = _stage(
        "inspect", "shared.scene_inspector", common,
        blend_file=str(blend), blender_exe=blender_exe, addons=addons,
        kit_root=root, timeout_sec=timeout_sec,
    )
    stages.append(inspect_stage)
    if inspect_stage["status"] != "ok":
        return _failed("inspect", stages, total_started)

    qa_args = [*common, "--asset-class", asset_class]
    qa_stage = _stage(
        "qa", "shared.qa_checks", qa_args,
        blend_file=str(blend), blender_exe=blender_exe, addons=addons,
        kit_root=root, timeout_sec=timeout_sec,
    )
    qa_passed = bool(qa_stage["result"].get("passed", False))
    qa_stage["gate_passed"] = qa_passed
    if not qa_passed:
        qa_stage["status"] = "error"
    stages.append(qa_stage)
    if not qa_passed and not continue_on_qa_error:
        result = _failed("qa", stages, total_started)
        result["qa_gate"] = {
            "passed": False,
            "override_used": False,
            "expensive_stages_skipped": True,
        }
        result["retry"] = {
            "recommended_from": "inspect",
            "message": "Fix QA findings, then rerun deliver. Inspect and QA are intentionally re-executed.",
        }
        return result

    if pack_input_dir:
        if not asset_id or not material:
            return _preflight_after_stages(
                "pack",
                "pack_input_dir requires both --asset-id and --material",
                stages,
                total_started,
            )
        pack_args = [
            "--target", target,
            "--asset-id", asset_id,
            "--material", material,
            "--input-dir", pack_input_dir,
            "--out", str(output / "packed"),
        ]
        if texture_profile:
            pack_args += ["--profile", texture_profile]
        if project_profile:
            pack_args += ["--project-profile", project_profile]
        if pack_size is not None:
            pack_args += ["--size", str(pack_size)]
        if detect_normal_y:
            pack_args.append("--detect-normal-y")
        pack_stage = _stage(
            "pack", "shared.channel_pack", pack_args,
            blend_file=None, blender_exe=blender_exe, addons=addons,
            kit_root=root, timeout_sec=timeout_sec,
        )
        stages.append(pack_stage)
        if pack_stage["status"] != "ok":
            return _failed("pack", stages, total_started)

    if not no_review:
        review_args = [
            "--target", target,
            "--style", review_style,
            "--device", device,
            "--out", str(output / "review"),
        ]
        if project_profile:
            review_args += ["--project-profile", project_profile]
        if review_preset:
            review_args += ["--preset", review_preset]
        if reference_fbx:
            review_args += ["--reference-fbx", reference_fbx]
        review_stage = _stage(
            "review", "shared.review_shots", review_args,
            blend_file=str(blend), blender_exe=blender_exe, addons=addons,
            kit_root=root, timeout_sec=timeout_sec,
        )
        stages.append(review_stage)
        if review_stage["status"] != "ok":
            return _failed("review", stages, total_started)

    if not no_export:
        export_dir = output / "export"
        if bundle_spec:
            export_args = [
                "--spec", bundle_spec,
                "--target", target,
                "--out", str(export_dir),
            ]
            if texture_profile:
                export_args += ["--profile", texture_profile]
            if project_profile:
                export_args += ["--project-profile", project_profile]
            export_stage = _stage(
                "bundle", "shared.bundle_exporter", export_args,
                blend_file=str(blend), blender_exe=blender_exe, addons=addons,
                kit_root=root, timeout_sec=timeout_sec,
            )
        else:
            export_args = ["--target", target, "--out", str(export_dir)]
            if texture_profile:
                export_args += ["--profile", texture_profile]
            if project_profile:
                export_args += ["--project-profile", project_profile]
            if asset_id:
                export_args += ["--asset-id", asset_id]
            export_args += [
                "--category", export_category or asset_class,
                "--rig-type", rig_type,
                "--uv1-source", uv1_source,
            ]
            export_stage = _stage(
                "export", "shared.exporter", export_args,
                blend_file=str(blend), blender_exe=blender_exe, addons=addons,
                kit_root=root, timeout_sec=timeout_sec,
            )
        stages.append(export_stage)
        if export_stage["status"] != "ok":
            return _failed(export_stage["name"], stages, total_started)

    total_ms = round((time.perf_counter() - total_started) * 1000.0, 3)
    return {
        "status": "ok",
        "qa_gate": {
            "passed": qa_passed,
            "override_used": bool(continue_on_qa_error and not qa_passed),
            "expensive_stages_skipped": False,
        },
        "duration_ms": total_ms,
        "stages": stages,
        "artifacts_root": str(output),
        "retry": {
            "recommended_from": "inspect",
            "message": "Reruns intentionally repeat inspect+QA before expensive stages.",
        },
    }


def _failed(stage: str, stages: list[dict], started: float) -> dict:
    return {
        "status": "error",
        "failed_stage": stage,
        "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "stages": stages,
    }


def _preflight_after_stages(
    stage: str,
    error: str,
    stages: list[dict],
    started: float,
) -> dict:
    result = _failed(stage, stages, started)
    result["error"] = error
    return result


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser(description="QA-gated Blender Agent Kit delivery orchestration.")
    p.add_argument("--blend", required=True)
    p.add_argument("--blender", default=None)
    p.add_argument("--addons", default=None)
    p.add_argument("--target", default="unity")
    p.add_argument("--asset-class", default="solid_prop")
    p.add_argument("--profile", default=None)
    p.add_argument("--project-profile", default=None)
    p.add_argument("--out", default="delivery")
    p.add_argument("--device", choices=["auto", "gpu", "cpu"], default="auto")
    p.add_argument("--review-style", default="technical")
    p.add_argument("--review-preset", default=None)
    p.add_argument("--reference-fbx", default=None)
    p.add_argument("--bundle-spec", default=None)
    p.add_argument("--asset-id", default=None)
    p.add_argument("--export-category", default=None)
    p.add_argument("--rig-type", default="none")
    p.add_argument("--uv1-source", default="blender")
    p.add_argument("--pack-input-dir", default=None)
    p.add_argument("--material", default=None)
    p.add_argument("--pack-size", type=int, default=None)
    p.add_argument("--detect-normal-y", action="store_true")
    p.add_argument("--no-review", action="store_true")
    p.add_argument("--no-export", action="store_true")
    p.add_argument("--continue-on-qa-error", action="store_true")
    p.add_argument("--timeout-sec", type=int, default=600)
    ns = p.parse_args(argv)
    addons = [v.strip() for v in ns.addons.split(",") if v.strip()] if ns.addons else None
    return run(
        blend_file=ns.blend,
        target=ns.target,
        asset_class=ns.asset_class,
        texture_profile=ns.profile,
        project_profile=ns.project_profile,
        out_dir=ns.out,
        blender_exe=ns.blender,
        addons=addons,
        device=ns.device,
        review_style=ns.review_style,
        review_preset=ns.review_preset,
        reference_fbx=ns.reference_fbx,
        bundle_spec=ns.bundle_spec,
        asset_id=ns.asset_id,
        export_category=ns.export_category,
        rig_type=ns.rig_type,
        uv1_source=ns.uv1_source,
        pack_input_dir=ns.pack_input_dir,
        material=ns.material,
        pack_size=ns.pack_size,
        detect_normal_y=ns.detect_normal_y,
        no_review=ns.no_review,
        no_export=ns.no_export,
        continue_on_qa_error=ns.continue_on_qa_error,
        timeout_sec=ns.timeout_sec,
    )
