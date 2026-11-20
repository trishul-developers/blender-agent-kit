---
name: blender-modeling
description: Use when creating or refining Blender meshes, props, or modular kits. The resolved contract supplies units, naming, pivot, budget, and QA rules.
---

# Blender Modeling

Before authoring, obtain the production contract with `run.py contract`.

- Author deterministic Blender/Python source and retain it with the `.blend`.
- Use the contract's units, naming, pivot/ground, material, and geometry rules; do not assume a universal prop convention.
- Keep topology intentional and modifiers non-destructive while iterating.
- Before QA/export, satisfy the contract's transform rules (including applied/negative scale requirements).
- Re-run QA after geometry, hierarchy, or transform changes.

Asset dimensions and content semantics come from the brief/project profile, not this core skill.
