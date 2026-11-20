"""Blender-free subcommand help based on the executable's own argument declarations."""
from __future__ import annotations

import ast
from pathlib import Path


def _value(node: ast.AST):
    if isinstance(node, ast.Constant):
        return node.value
    return None


def render_subcommand_help(kit_root: Path, command: str, module_name: str, mode: str = "blender") -> str:
    path = kit_root.joinpath(*module_name.split(".")).with_suffix(".py")
    source = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next((node for node in source.body if isinstance(node, ast.FunctionDef)
                     and node.name == "cli_main"), None)
    if function is None:
        raise ValueError(f"No cli_main declaration in {module_name}")
    args = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "add_argument":
            continue
        names = [_value(v) for v in node.args]
        names = [x for x in names if isinstance(x, str)]
        if not names:
            continue
        props = {k.arg: _value(k.value) for k in node.keywords if k.arg}
        if all(n.startswith("-") for n in names):
            name = ", ".join(names)
            if props.get("action") not in ("store_true", "store_false"):
                name += " VALUE"
        else:
            name = ", ".join(names)
        desc = str(props.get("help") or "")
        if props.get("required") is True:
            desc += " (required)"
        elif props.get("default") is not None:
            desc += f" (default: {props['default']})"
        args.append((name, desc.strip()))
    width = max((len(name) for name, _ in args), default=0)
    body = "\n".join(f"  {name.ljust(width)}  {desc}".rstrip() for name, desc in args)
    entry_options = (
        "--result-json FILE"
        if mode == "host"
        else "--blend FILE --blender FILE --addons IDS --result-json FILE"
    )
    return (
        f"Blender Agent Kit: {command}\n"
        f"  python skills/core/blender-core/scripts/run.py {command} [OPTIONS]\n\n"
        f"Host options: {entry_options}\n"
        f"Execution mode: {mode}\n"
        f"Subcommand options (from {module_name}.cli_main):\n"
        f"{body}\n"
    )
