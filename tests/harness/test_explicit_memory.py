"""Explicit layouts and index assertions must preserve the declared contract."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import contract


class ExplicitMemory(unittest.TestCase):
    def setUp(self):
        self.path = contract.ROOT / "tests/contracts/buffer-memory-selection/unchanged-layout.yaml"
        self.case = contract.load_case(self.path)
        self.config = {
            "memory-heaps": [{"size": 1073741824, "flags": ["DEVICE_LOCAL"]},
                             {"size": 134217728, "flags": ["DEVICE_LOCAL"]}],
            "memory-types": [{"heap": heap, "properties": properties}
                             for heap, properties in zip((0, 0, 0, 1), self.case["capture"]["memory-types"])]}

    def load_modified_case(self, case):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "description.yaml"
            path.write_text(contract.yaml.safe_dump(case))
            return contract.load_case(path)

    def observations(self):
        stages = {}
        for stage in ("capture", "replay"):
            config = self.case[stage]
            layout = contract.memory_layout(config["memory-types"], config.get("memory-heaps"))
            bindings = [{"name": name, "uid": uid, "allocation_uid": uid + 10,
                         "memory_type_index": index, "memory_offset": 0}
                        for uid, (name, index) in enumerate(
                            [("upload-buffer", 0), ("readback-buffer", 1), ("optimal-image", 0)])]
            raw = {"physical_devices": [layout | {"devices": [{"memory_bindings": bindings}]}]}
            stages[stage] = contract.normalize(raw, self.case["observe"])
        return {"stages": stages}

    def test_common_layout_has_two_distinct_device_local_heaps(self):
        layout = contract.memory_layout(self.config["memory-types"], self.config["memory-heaps"])
        self.assertEqual(contract.memory_layout(self.case["capture"]["memory-types"]), layout)
        self.assertEqual(layout, {
            "memory_types": [{"heap_index": 0, "property_flags": 7},
                             {"heap_index": 0, "property_flags": 11},
                             {"heap_index": 0, "property_flags": 17},
                             {"heap_index": 1, "property_flags": 33}],
            "memory_heaps": [{"size": 1073741824, "flags": 1}, {"size": 134217728, "flags": 1}]})

    def test_generated_profile_preserves_heap_indices_and_other_capabilities(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base"
            base.mkdir()
            (base / "gpu.json").write_text('{"base": true}')
            (base / "gpu_override.json").write_text('{"capabilities": {"device": {"features": {"sentinel": true}}}}')
            destination = root / "generated"
            contract.make_profile(base, destination, self.config["memory-types"], self.config["memory-heaps"])
            generated = json.loads((destination / "gpu_override.json").read_text())["capabilities"]["device"]
            self.assertTrue(generated["features"]["sentinel"])
            memory = generated["properties"]["VkPhysicalDeviceMemoryProperties"]
            self.assertEqual(memory["memoryTypeCount"], 4)
            self.assertEqual(memory["memoryHeapCount"], 2)
            self.assertEqual([t["heapIndex"] for t in memory["memoryTypes"]], [0, 0, 0, 1])
            self.assertEqual(memory["memoryHeaps"][1]["size"], 134217728)
            self.assertEqual(json.loads((destination / "gpu.json").read_text()), {"base": True})

    def test_duplicate_property_types_keep_their_positions(self):
        types = copy.deepcopy(self.config["memory-types"])
        types.append(copy.deepcopy(types[0]))
        layout = contract.memory_layout(types, self.config["memory-heaps"])
        self.assertEqual(len(layout["memory_types"]), 5)
        self.assertEqual(layout["memory_types"][0], layout["memory_types"][4])

    def test_invalid_heap_references_are_rejected(self):
        for index in (-1, 2, True, 0.5):
            with self.subTest(index=index):
                case = copy.deepcopy(self.case)
                case["capture"] = copy.deepcopy(self.config)
                case["capture"]["memory-types"][0]["heap"] = index
                with self.assertRaises(ValueError):
                    self.load_modified_case(case)

    def test_type_and_heap_locality_must_agree(self):
        for properties, flags in ((["DEVICE_LOCAL"], []),
                                  (["HOST_VISIBLE", "HOST_COHERENT"], ["DEVICE_LOCAL"])):
            with self.subTest(properties=properties, flags=flags):
                case = copy.deepcopy(self.case)
                case["capture"] = {
                    "memory-types": [{"heap": 0, "properties": properties}],
                    "memory-heaps": [{"size": 1024, "flags": flags}]}
                with self.assertRaisesRegex(ValueError, "flags must agree"):
                    self.load_modified_case(case)

    def test_invalid_heaps_are_rejected(self):
        for heaps in (None, [], [{"size": 0, "flags": []}],
                      [{"size": True, "flags": []}],
                      [{"size": 1024, "flags": ["HOST_VISIBLE"]}]):
            with self.subTest(heaps=heaps):
                case = copy.deepcopy(self.case)
                case["capture"] = copy.deepcopy(self.config)
                case["capture"]["memory-heaps"] = heaps
                with self.assertRaises(ValueError):
                    self.load_modified_case(case)

    def test_mixed_type_formats_are_rejected(self):
        case = copy.deepcopy(self.case)
        case["capture"] = copy.deepcopy(self.config)
        case["capture"]["memory-types"][0] = ["DEVICE_LOCAL"]
        with self.assertRaises(ValueError):
            self.load_modified_case(case)

    def test_equivalent_platform_properties_pass(self):
        result = contract.validate(self.case, self.observations())
        self.assertEqual(result["status"], "PASS")

    def test_wrong_index_fails_despite_matching_properties(self):
        self.case["expect"]["upload-buffer"] = {"memory-type-index": 0}
        report = self.observations()
        # Another type with identical properties must not replace captured index 0.
        for stage in ("capture", "replay"):
            config = self.case[stage]
            config["memory-types"].append(copy.deepcopy(config["memory-types"][0]))
            report["stages"][stage]["memory_types"].append(
                copy.deepcopy(report["stages"][stage]["memory_types"][0]))
        report["stages"]["replay"]["objects"]["upload-buffer"][0]["memory_type_index"] = 4
        result = contract.validate(self.case, report)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(next(c for c in result["checks"] if c["status"] == "FAIL")["check"], "replay/upload-buffer")

    def test_property_expectation_accepts_another_type_with_identical_flags(self):
        report = self.observations()
        for stage in ("capture", "replay"):
            self.case[stage]["memory-types"].append(copy.deepcopy(self.case[stage]["memory-types"][0]))
            report["stages"][stage]["memory_types"].append(
                copy.deepcopy(report["stages"][stage]["memory_types"][0]))
        report["stages"]["replay"]["objects"]["upload-buffer"][0]["memory_type_index"] = 4
        self.assertEqual(contract.validate(self.case, report)["status"], "PASS")

    def test_capture_expectations_are_rejected(self):
        case = copy.deepcopy(self.case)
        case["capture"]["expect"] = {"upload-buffer": {"memory-type-index": 0}}
        with self.assertRaises(ValueError):
            self.load_modified_case(case)

    def test_invalid_expected_indices_are_rejected(self):
        for index in (-1, 4, True):
            with self.subTest(index=index):
                case = copy.deepcopy(self.case)
                case["expect"]["upload-buffer"] = {"memory-type-index": index}
                with self.assertRaises(ValueError):
                    self.load_modified_case(case)

    def test_adjacent_workload_exists(self):
        source = self.path.parent / "workload.cpp"
        self.assertTrue(source.is_file())

    def test_legacy_inline_format_is_unchanged(self):
        legacy = contract.load_case(contract.ROOT / "tests/contracts/buffer-memory-selection/split-host-visible-types.yaml")
        layout = contract.memory_layout(legacy["capture"]["memory-types"])
        self.assertEqual(layout, {"memory_types": [{"heap_index": 0, "property_flags": 15}],
                                  "memory_heaps": [{"size": 1073741824, "flags": 1}]})


if __name__ == "__main__":
    unittest.main()
