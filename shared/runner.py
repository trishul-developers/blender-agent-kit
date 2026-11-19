"""Host-side headless Blender orchestrator (Python 3.10+ stdlib only)."""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from shared.paths import resolve_kit_root

SUBCOMMAND_TO_MODULE = {
    "doctor": "tools.doctor_blender",
    "qa": "shared.qa_checks",
    "pack": "shared.channel_pack",
    "export": "shared.exporter",
    "review": "shared.review_shots",
}


def find_blender(explicit: str | None = None) -> str:
    """Locate a Blender executable from explicit arg, BLENDER_EXECUTABLE, PATH, or standard install dirs."""
    candidates: list[Path] = []
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return str(p)
        raise FileNotFoundError(f"Configured Blender executable not found: {explicit}")

    env_bin = os.environ.get("BLENDER_EXECUTABLE")
    if env_bin:
        p = Path(env_bin)
        if p.is_file():
            return str(p)
        raise FileNotFoundError(f"BLENDER_EXECUTABLE points to missing file: {env_bin}")

    which_bin = shutil.which("blender")
    if which_bin:
        return which_bin

    system = platform.system()
    if system == "Darwin":
        candidates.append(Path("/Applications/Blender.app/Contents/MacOS/Blender"))
    elif system == "Windows":
        pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
        if pf.is_dir():
            for d in sorted(pf.glob("Blender 5.*"), reverse=True):
                candidates.append(d / "blender.exe")
            for d in sorted(pf.glob("Blender *"), reverse=True):
                candidates.append(d / "blender.exe")
    else:
        candidates.extend([
            Path("/usr/local/bin/blender"),
            Path("/usr/bin/blender"),
            Path("/snap/bin/blender"),
        ])

    for c in candidates:
        if c.is_file():
            return str(c)

    raise FileNotFoundError(
        "Blender executable not found. Set BLENDER_EXECUTABLE or add blender to PATH."
    )


def build_blender_command(
    blender_exe: str,
    kit_root: Path,
    module_name: str,
    module_args: list[str],
    result_json: Path,
    blend_file: str | None = None,
    addons: list[str] | None = None,
) -> list[str]:
    """Build a strictly ordered headless Blender CLI invocation.

    Order guarantee: -b -> [blend_file] -> --factory-startup -> [--addons ...] ->
    --python-exit-code 1 -> -P bootstrap.py -> -- -> bootstrap & module args.
    """
    cmd: list[str] = [blender_exe, "-b"]
    if blend_file:
        cmd.append(str(Path(blend_file).resolve()))
    cmd.append("--factory-startup")
    if addons:
        cmd.extend(["--addons", ",".join(addons)])
    cmd.extend([
        "--python-exit-code", "1",
        "-P", str((kit_root / "shared" / "bootstrap.py").resolve()),
        "--",
        "--kit-root", str(kit_root.resolve()),
        "--module", module_name,
        "--result-json", str(result_json.resolve()),
        *module_args,
    ])
    return cmd


def run_blender_module(
    module_name: str,
    module_args: list[str] | None = None,
    blend_file: str | None = None,
    addons: list[str] | None = None,
    blender_exe: str | None = None,
    kit_root: Path | None = None,
    log_dir: Path | None = None,
    timeout_sec: int = 600,
) -> dict:
    """Execute a kit module inside headless Blender and return the structured JSON result."""
    root = kit_root or resolve_kit_root()
    exe = find_blender(blender_exe)

    with tempfile.TemporaryDirectory(prefix="bak_run_") as tmpdir:
        tmp_path = Path(tmpdir)
        result_file = tmp_path / "result.json"
        cmd = build_blender_command(
            blender_exe=exe,
            kit_root=root,
            module_name=module_name,
            module_args=module_args or [],
            result_json=result_file,
            blend_file=blend_file,
            addons=addons,
        )
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )

        payload: dict | None = None
        if result_file.is_file():
            payload = json.loads(result_file.read_text(encoding="utf-8"))
        else:
            for line in reversed(proc.stdout.splitlines()):
                if line.startswith("@@JSON@@"):
                    payload = json.loads(line[len("@@JSON@@"):])
                    break

        if payload is None:
            payload = {
                "status": "error",
                "error": f"Blender exited with code {proc.returncode} without writing result JSON.",
            }

        if proc.returncode != 0 or payload.get("status") != "ok":
            payload["status"] = "error"
            payload["returncode"] = proc.returncode
            log_base = log_dir or Path(tempfile.gettempdir()) / "blender-agent-kit-logs"
            log_base.mkdir(parents=True, exist_ok=True)
            log_file = log_base / f"{module_name.replace('.', '_')}_{os.getpid()}.log"
            log_file.write_text(
                f"CMD: {' '.join(cmd)}\n\n=== STDOUT ===\n{proc.stdout}\n\n=== STDERR ===\n{proc.stderr}\n",
                encoding="utf-8",
            )
            payload["log_file"] = str(log_file)

        return payload
