"""Validation must distinguish wrong behavior from incomplete observations."""
import copy
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import contract


class ContractValidation(unittest.TestCase):
    def setUp(self):
        path = contract.ROOT / "tests/contracts/buffer-memory-selection/split-host-visible-types.yaml"
        self.case = contract.load_case(path)
        self.report = {"stages": {}}
        for stage in ("capture", "replay"):
            layout = contract.memory_layout(self.case[stage]["memory-types"])
            bindings = []
            for uid, name in enumerate(self.case["observe"]):
                index = 0 if stage == "capture" or name == "optimal-image" else 2
                bindings.append({"uid": uid, "name": name, "allocation_uid": 10 + uid,
                                 "memory_type_index": index, "memory_offset": 0,
                                 "kind": "image" if name == "optimal-image" else "buffer"})
            raw = {"physical_devices": [layout | {"devices": [{"memory_bindings": bindings}]}]}
            self.report["stages"][stage] = contract.normalize(raw, self.case["observe"])

    def test_selected_properties_match_expectations(self):
        self.assertEqual(contract.evaluate(self.case, self.report)["status"], "SUBOPTIMAL")

    def test_local_image_accepts_additional_host_visible_properties(self):
        self.report["stages"]["replay"]["objects"]["optimal-image"][0]["properties"] = [
            "DEVICE_LOCAL", "HOST_VISIBLE", "HOST_COHERENT"]
        result = contract.evaluate(self.case, self.report)
        self.assertEqual(next(a for a in result["assessments"] if a["resource"] == "optimal-image")["status"], "OPTIMAL")

    def test_host_coherence_is_required_not_just_visibility(self):
        self.report["stages"]["replay"]["objects"]["upload-buffer-unflushed"][0]["properties"] = ["HOST_VISIBLE", "HOST_CACHED"]
        self.assertEqual(contract.evaluate(self.case, self.report)["status"], "ISSUE")

    def test_nonlocal_image_and_uncached_readback_are_suboptimal(self):
        self.report["stages"]["replay"]["objects"]["optimal-image"][0]["properties"] = ["HOST_VISIBLE", "HOST_COHERENT"]
        result = contract.evaluate(self.case, self.report)
        self.assertEqual(result["status"], "SUBOPTIMAL")
        self.assertEqual([a["status"] for a in result["assessments"]],
                         ["OPTIMAL", "OPTIMAL", "OPTIMAL", "SUBOPTIMAL", "SUBOPTIMAL"])

    def test_cached_and_coherent_readback_is_optimal(self):
        self.report["stages"]["replay"]["objects"]["readback-buffer"][0]["properties"] = ["HOST_VISIBLE", "HOST_COHERENT", "HOST_CACHED"]
        self.assertEqual(contract.evaluate(self.case, self.report)["status"], "OPTIMAL")

    def test_wrong_resource_kind_is_inconclusive(self):
        self.report["stages"]["replay"]["objects"]["optimal-image"][0]["kind"] = "buffer"
        self.assertEqual(contract.evaluate(self.case, self.report)["status"], "INCONCLUSIVE")

    def test_missing_object_is_inconclusive(self):
        self.report["stages"]["replay"]["objects"]["optimal-image"] = []
        self.assertEqual(contract.evaluate(self.case, self.report)["status"], "INCONCLUSIVE")

    def test_duplicate_names_are_not_resolved_by_creation_order(self):
        objects = self.report["stages"]["replay"]["objects"]["upload-buffer-unflushed"]
        objects.append(copy.deepcopy(objects[0]) | {"uid": 99})
        self.assertEqual(contract.evaluate(self.case, self.report)["status"], "INCONCLUSIVE")

    def test_unbound_named_object_is_inconclusive(self):
        del self.report["stages"]["replay"]["objects"]["readback-buffer"][0]["allocation_uid"]
        self.assertEqual(contract.evaluate(self.case, self.report)["status"], "INCONCLUSIVE")

    def test_wrong_driver_environment_fails_even_with_matching_objects(self):
        self.report["stages"]["replay"]["memory_types"][0]["property_flags"] = 15
        self.assertEqual(contract.evaluate(self.case, self.report)["status"], "FAIL")

    def test_assessment_is_independent_of_environment_validation(self):
        assessments = contract.assess(self.case, self.report)
        self.report["stages"]["replay"]["memory_types"][0]["property_flags"] = 15
        self.assertEqual(contract.assess(self.case, self.report), assessments)
        self.assertEqual(contract.validate(self.case, self.report, assessments)["status"], "FAIL")

    def test_validation_applies_policy_to_existing_assessments(self):
        assessments = contract.assess(self.case, self.report)
        self.assertEqual(contract.validate(self.case, self.report, assessments)["status"], "SUBOPTIMAL")
        assessments[0] = assessments[0] | {"status": "ISSUE"}
        self.assertEqual(contract.validate(self.case, self.report, assessments)["status"], "ISSUE")

    def test_successful_subprocess_is_not_sufficient(self):
        self.assertEqual(contract.evaluate(self.case, {"stages": {}})["status"], "INCONCLUSIVE")

    def test_subprocess_error_cannot_pass(self):
        self.report["error"] = "replay failed"
        self.assertEqual(contract.evaluate(self.case, self.report)["status"], "ERROR")

    def test_capability_skip_is_not_a_pass(self):
        self.report["skip"] = "workload exited 77"
        self.assertEqual(contract.evaluate(self.case, self.report)["status"], "SKIP")

    def test_duplicate_yaml_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            contract.yaml.load("expect: {}\nexpect: {}\n", Loader=contract.CaseLoader)

    def test_tags_are_optional_and_must_be_distinct_nonempty_strings(self):
        for tags, valid in ((None, True), ([], True), (["synthetic"], True),
                            (["future-tag"], True), ("synthetic", False),
                            ([""], False), (["synthetic", "synthetic"], False), ([1], False)):
            with self.subTest(tags=tags), tempfile.TemporaryDirectory() as directory:
                case = copy.deepcopy(self.case)
                if tags is None:
                    case.pop("tags", None)
                else:
                    case["tags"] = tags
                path = Path(directory) / "case.yaml"
                path.write_text(contract.yaml.safe_dump(case))
                if valid:
                    contract.load_case(path)
                else:
                    with self.assertRaisesRegex(ValueError, "tags must be"):
                        contract.load_case(path)

    def test_names_select_the_assessments(self):
        self.assertEqual(set(self.case["observe"].values()), {"memory-type"})
        self.assertEqual(contract.assessments_for(self.case), {
            "upload-buffer-unflushed": "upload-buffer-unflushed",
            "upload-buffer-storage-unflushed": "upload-buffer-storage-unflushed",
            "upload-buffer-vertex-unflushed": "upload-buffer-vertex-unflushed",
            "readback-buffer": "readback-buffer", "optimal-image": "optimal-image"})

    def test_each_upload_reports_loss_of_coherence(self):
        for name in ("upload-buffer-unflushed", "upload-buffer-storage-unflushed",
                     "upload-buffer-vertex-unflushed"):
            with self.subTest(name=name):
                report = copy.deepcopy(self.report)
                report["stages"]["replay"]["objects"][name][0]["properties"] = ["HOST_VISIBLE", "HOST_CACHED"]
                assessment = next(a for a in contract.assess(self.case, report) if a["resource"] == name)
                self.assertEqual(assessment["status"], "ISSUE")

    def test_unknown_observation_requires_an_expectation(self):
        case = copy.deepcopy(self.case)
        case["observe"]["unknown-buffer"] = "memory-type"
        with self.assertRaisesRegex(ValueError, "no assessment"):
            contract.assessments_for(case)

    def test_previous_inline_roles_remain_readable(self):
        case = copy.deepcopy(self.case)
        case["observe"] = {"upload-buffer": "upload-unflushed",
                           "readback-buffer": "readback", "optimal-image": "optimal-image"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "description.yaml"
            path.write_text(contract.yaml.safe_dump(case))
            loaded = contract.load_case(path)
            self.assertEqual(contract.assessments_for(loaded), case["observe"])


if __name__ == "__main__":
    unittest.main()
