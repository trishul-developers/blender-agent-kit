// Drop into Assets/Editor/BlenderAssetPostprocessor.cs in your Unity project.
// 2-stage postprocessor reading sibling *.asset.manifest.json (schema_version 1.0)
// to avoid texture/model import-order races and URP Lit smoothness-multiplier bugs.

#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace BlenderAgentKit.Editor
{
    [Serializable]
    public class AssetManifestV1
    {
        public string schema_version;
        public string asset_id;
        public string category;
        public string target;
        public string profile;
        public string rig_type;
        public string uv1_source;
        public string export_file;
        public bool disable_unity_auto_mesh_lod;
        public LodEntry[] lods;
        public ColliderEntry[] colliders;
        public MaterialEntry[] materials;
        public TextureEntry[] textures;
    }

    [Serializable]
    public class LodEntry
    {
        public string name;
        public int tri_count;
        public float screen_relative_transition_height;
    }

    [Serializable]
    public class ColliderEntry
    {
        public string node_name;
        public string shape;
        public bool strip_renderer;
    }

    [Serializable]
    public class MaterialEntry
    {
        public string material_name;
        public string shader;
        // Unity JsonUtility does not deserialize arbitrary Dictionary<string,string>;
        // extend with explicit slot fields or Newtonsoft.Json if installed.
    }

    [Serializable]
    public class TextureEntry
    {
        public string material_name;
        public string path;
        public bool srgb;
        public int bit_depth;
        public bool normal_map;
        public int max_size;
    }

    public class BlenderAssetPostprocessor : AssetPostprocessor
    {
        private const uint PostprocessorVersion = 1;

        public override uint GetVersion() => PostprocessorVersion;

        private static bool TryLoadManifestForAsset(string assetPath, out AssetManifestV1 manifest, out string manifestDir)
        {
            manifest = null;
            manifestDir = Path.GetDirectoryName(assetPath) ?? "";
            if (string.IsNullOrEmpty(manifestDir) || !Directory.Exists(manifestDir))
                return false;

            // Check sibling directory and parent directory (for textures/ subfolder)
            string[] searchDirs = { manifestDir, Path.GetDirectoryName(manifestDir) ?? "" };
            foreach (var dir in searchDirs)
            {
                if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) continue;
                foreach (var file in Directory.GetFiles(dir, "*.asset.manifest.json"))
                {
                    try
                    {
                        var json = File.ReadAllText(file);
                        var parsed = JsonUtility.FromJson<AssetManifestV1>(json);
                        if (parsed != null && parsed.schema_version == "1.0")
                        {
                            manifest = parsed;
                            manifestDir = dir;
                            return true;
                        }
                    }
                    catch (Exception ex)
                    {
                        Debug.LogWarning($"[BlenderAgentKit] Failed parsing {file}: {ex.Message}");
                    }
                }
            }
            return false;
        }

        // Stage 1a: Configure TextureImporter before textures are imported (file-system read only)
        private void OnPreprocessTexture()
        {
            if (!TryLoadManifestForAsset(assetPath, out var manifest, out var manifestDir))
                return;
            if (manifest.textures == null) return;

            string normAsset = assetPath.Replace("\\", "/");
            foreach (var tex in manifest.textures)
            {
                string expected = Path.Combine(manifestDir, tex.path).Replace("\\", "/");
                if (!string.Equals(normAsset, expected, StringComparison.OrdinalIgnoreCase))
                    continue;

                var importer = (TextureImporter)assetImporter;
                importer.sRGBTexture = tex.srgb;
                importer.textureType = tex.normal_map
                    ? TextureImporterType.NormalMap
                    : TextureImporterType.Default;
                importer.maxTextureSize = Mathf.Max(32, tex.max_size);
                break;
            }
        }

        // Stage 1b: Configure ModelImporter before model import
        private void OnPreprocessModel()
        {
            if (!TryLoadManifestForAsset(assetPath, out var manifest, out _))
                return;
            if (!assetPath.EndsWith(manifest.export_file, StringComparison.OrdinalIgnoreCase))
                return;

            var importer = (ModelImporter)assetImporter;
            importer.globalScale = 1.0f;
            importer.useFileUnits = true;
            importer.bakeAxisConversion = !string.Equals(manifest.rig_type, "none", StringComparison.OrdinalIgnoreCase);
            importer.generateSecondaryUV = string.Equals(manifest.uv1_source, "unity_generate", StringComparison.OrdinalIgnoreCase);
            importer.importAnimation = !string.Equals(manifest.rig_type, "none", StringComparison.OrdinalIgnoreCase);

            if (string.Equals(manifest.rig_type, "humanoid", StringComparison.OrdinalIgnoreCase))
            {
                importer.animationType = ModelImporterAnimationType.Human;
                importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            }
            else if (string.Equals(manifest.rig_type, "generic", StringComparison.OrdinalIgnoreCase))
            {
                importer.animationType = ModelImporterAnimationType.Generic;
            }
            else
            {
                importer.animationType = ModelImporterAnimationType.None;
            }

#if UNITY_6000_2_OR_NEWER
            // Prevent Unity 6.2+ auto Mesh LOD from conflicting with FBX _LOD0/_LOD1 LODGroups
            importer.generateMeshLods = !manifest.disable_unity_auto_mesh_lod;
#endif
        }

        // Stage 2: Runs after all textures and models in the batch finish importing
        private static void OnPostprocessAllAssets(
            string[] importedAssets,
            string[] deletedAssets,
            string[] movedAssets,
            string[] movedFromAssetPaths)
        {
            var processedManifests = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var path in importedAssets)
            {
                if (!path.EndsWith(".asset.manifest.json", StringComparison.OrdinalIgnoreCase) &&
                    !path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase) &&
                    !path.EndsWith(".glb", StringComparison.OrdinalIgnoreCase))
                    continue;

                if (!TryLoadManifestForAsset(path, out var manifest, out var manifestDir))
                    continue;
                string key = Path.Combine(manifestDir, manifest.asset_id);
                if (!processedManifests.Add(key))
                    continue;

                ConfigureMaterialsForManifest(manifest, manifestDir);
            }
        }

        private static void ConfigureMaterialsForManifest(AssetManifestV1 manifest, string manifestDir)
        {
            if (manifest.textures == null || manifest.textures.Length == 0)
                return;

            var byMaterial = new Dictionary<string, List<TextureEntry>>(StringComparer.OrdinalIgnoreCase);
            foreach (var t in manifest.textures)
            {
                if (!byMaterial.TryGetValue(t.material_name, out var list))
                {
                    list = new List<TextureEntry>();
                    byMaterial[t.material_name] = list;
                }
                list.Add(t);
            }

            bool isHdrp = string.Equals(manifest.profile, "hdrp", StringComparison.OrdinalIgnoreCase);
            Shader shader = Shader.Find(isHdrp ? "HDRP/Lit" : "Universal Render Pipeline/Lit");
            if (shader == null) return;

            string matDir = Path.Combine(manifestDir, "Materials").Replace("\\", "/");
            if (!Directory.Exists(matDir)) Directory.CreateDirectory(matDir);

            foreach (var kvp in byMaterial)
            {
                string matPath = $"{matDir}/{kvp.Key}.mat";
                Material mat = AssetDatabase.LoadAssetAtPath<Material>(matPath);
                if (mat == null)
                {
                    mat = new Material(shader);
                    AssetDatabase.CreateAsset(mat, matPath);
                }

                // URP Lit smoothness-multiplier fix: explicitly set _Metallic=1 and _Smoothness=1
                // so Unity does not halve packed alpha smoothness (default 0.5).
                if (!isHdrp)
                {
                    mat.SetFloat("_Metallic", 1.0f);
                    mat.SetFloat("_Smoothness", 1.0f);
                    mat.SetFloat("_SmoothnessTextureChannel", 0.0f); // Metallic Alpha
                }

                foreach (var texEntry in kvp.Value)
                {
                    string texPath = Path.Combine(manifestDir, texEntry.path).Replace("\\", "/");
                    var tex2d = AssetDatabase.LoadAssetAtPath<Texture2D>(texPath);
                    if (tex2d == null) continue;

                    if (texEntry.path.Contains("__albedo") || texEntry.path.Contains("__base_map"))
                    {
                        mat.SetTexture(isHdrp ? "_BaseColorMap" : "_BaseMap", tex2d);
                    }
                    else if (texEntry.path.Contains("__metallic_smoothness"))
                    {
                        mat.SetTexture("_MetallicGlossMap", tex2d);
                        mat.EnableKeyword("_METALLICSPECGLOSSMAP");
                    }
                    else if (texEntry.path.Contains("__mask_map"))
                    {
                        mat.SetTexture("_MaskMap", tex2d);
                        mat.EnableKeyword("_MASKMAP");
                    }
                    else if (texEntry.normal_map)
                    {
                        mat.SetTexture(isHdrp ? "_NormalMap" : "_BumpMap", tex2d);
                        mat.EnableKeyword("_NORMALMAP");
                    }
                    else if (texEntry.path.Contains("__ao"))
                    {
                        mat.SetTexture("_OcclusionMap", tex2d);
                        mat.EnableKeyword("_OCCLUSIONMAP");
                    }
                }
                EditorUtility.SetDirty(mat);
            }
            AssetDatabase.SaveAssets();
        }
    }
}
#endif
