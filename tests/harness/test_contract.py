"""Validation must distinguish wrong behavior from incomplete observations."""
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import contract


class ContractValidation(unittest.TestCase):
    def setUp(self):
        self.case = contract.load_case(contract.ROOT / "tests/contracts/buffer-memory-selection/split-host-visible-types.yaml")
        self.report = {"stages": {}}
        for stage in ("capture", "replay"):
            layout = contract.memory_layout(self.case[stage]["memory-types"])
            bindings = []
            for uid, name in enumerate(self.case["observe"]):
                index = 0 if stage == "capture" or name == "optimal-image" else (1 if name == "readback-buffer" else 2)
                bindings.append({"uid": uid, "name": name, "allocation_uid": 10 + uid,
                                 "memory_type_index": index, "memory_offset": 0,
                                 "kind": "image" if name == "optimal-image" else "buffer"})
            raw = {"physical_devices": [layout | {"devices": [{"memory_bindings": bindings}]}]}
            self.report["stages"][stage] = contract.normalize(raw, self.case["observe"])

    def test_selected_properties_match_expectations(self):
        self.assertEqual(contract.validate(self.case, self.report)["status"], "PASS")

    def test_local_only_image_rejects_additional_host_visible_properties(self):
        self.report["stages"]["replay"]["objects"]["optimal-image"][0]["properties"] = [
            "DEVICE_LOCAL", "HOST_VISIBLE", "HOST_COHERENT"]
        self.assertEqual(contract.validate(self.case, self.report)["status"], "FAIL")

    def test_host_coherence_is_required_not_just_visibility(self):
        self.report["stages"]["replay"]["objects"]["upload-buffer"][0]["properties"] = ["HOST_VISIBLE", "HOST_CACHED"]
        self.assertEqual(contract.validate(self.case, self.report)["status"], "FAIL")

    def test_missing_object_is_inconclusive(self):
        self.report["stages"]["replay"]["objects"]["optimal-image"] = []
        self.assertEqual(contract.validate(self.case, self.report)["status"], "INCONCLUSIVE")

    def test_duplicate_names_are_not_resolved_by_creation_order(self):
        objects = self.report["stages"]["replay"]["objects"]["upload-buffer"]
        objects.append(copy.deepcopy(objects[0]) | {"uid": 99})
        self.assertEqual(contract.validate(self.case, self.report)["status"], "INCONCLUSIVE")

    def test_unbound_named_object_is_inconclusive(self):
        del self.report["stages"]["replay"]["objects"]["readback-buffer"][0]["allocation_uid"]
        self.assertEqual(contract.validate(self.case, self.report)["status"], "INCONCLUSIVE")

    def test_wrong_driver_environment_fails_even_with_matching_objects(self):
        self.report["stages"]["replay"]["memory_types"][0]["property_flags"] = 15
        self.assertEqual(contract.validate(self.case, self.report)["status"], "FAIL")

    def test_successful_subprocess_is_not_sufficient(self):
        self.assertEqual(contract.validate(self.case, {"stages": {}})["status"], "INCONCLUSIVE")

    def test_subprocess_error_cannot_pass(self):
        self.report["error"] = "replay failed"
        self.assertEqual(contract.validate(self.case, self.report)["status"], "ERROR")

    def test_capability_skip_is_not_a_pass(self):
        self.report["skip"] = "workload exited 77"
        self.assertEqual(contract.validate(self.case, self.report)["status"], "SKIP")

    def test_duplicate_yaml_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            contract.yaml.load("expect: {}\nexpect: {}\n", Loader=contract.CaseLoader)


if __name__ == "__main__":
    unittest.main()
