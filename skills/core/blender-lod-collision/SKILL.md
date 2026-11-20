---
name: blender-lod-collision
description: Use for LOD and collision authoring. LOD/collider naming, budgets, ratios, and exclusions come from the resolved production contract rather than hard-coded suffixes.
---

# Blender LOD & Collision

1. Read `contract.naming` and `contract.qa.lod` before generating levels or proxies.
2. Keep LOD triangle counts monotonic when required and verify silhouette, topology, UVs, materials, and deformation quality after simplification.
3. Choose simplification strategy from asset topology; do not assume one decimator is safe for every hard-surface, organic, or skinned mesh.
4. Author collision proxies using the configured collider patterns and project collision requirements.
5. Run QA after LOD/collision changes; collision geometry must not inflate visible render-LOD evidence.

Collider convexity/decomposition quality is not yet geometrically certified by core QA.
