"""Select the built capture manifest without confusing it with staging files."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import contract


class LayerManifest(unittest.TestCase):
    def test_source_build_prefers_manifest_beside_selected_library(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layer = root / "layer"
            staging = layer / "staging-json"
            staging.mkdir(parents=True)
            library = layer / "libVkLayer_gfxreconstruct.so"
            library.touch()
            manifest = layer / "VkLayer_gfxreconstruct.json"
            manifest.write_text('{"layer": {"library_path": "./libVkLayer_gfxreconstruct.so"}}')
            (staging / manifest.name).write_text('{"layer": {"library_path": "libVkLayer_gfxreconstruct.so"}}')
            self.assertEqual(contract.find_layer_manifest(root, library), manifest.resolve())

    def test_installed_manifest_can_be_separate_from_library(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            share = root / "share/vulkan/explicit_layer.d"
            share.mkdir(parents=True)
            manifest = share / "VkLayer_gfxreconstruct.json"
            manifest.touch()
            self.assertEqual(contract.find_layer_manifest(root, root / "lib/libVkLayer_gfxreconstruct.so"),
                             manifest.resolve())

    def test_ambiguous_fallback_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("first", "second"):
                (root / name).mkdir()
                (root / name / "VkLayer_gfxreconstruct.json").touch()
            with self.assertRaises(ValueError):
                contract.find_layer_manifest(root, root / "lib/libVkLayer_gfxreconstruct.so")


if __name__ == "__main__":
    unittest.main()
