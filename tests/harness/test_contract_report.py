"""Reports must preserve failures and link to the exact invocation's evidence."""
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import contract_report


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href")


class ContractReport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runs = self.root / "suite"
        self.run = self.runs / "case with spaces"
        self.run.mkdir(parents=True)
        (self.runs / "cases.txt").write_text("memory/combined.yaml\nmemory/missing.yaml\n")
        self.observed = {
            "case": "memory/combined", "description": '<script>alert("unsafe")</script>',
            "optimization": {"status": "not_needed", "replay_input": "input.gfxr", "reason": "No changes"},
            "stages": {"capture": {"objects": {"readback-buffer": [{"memory_type_index": 1,
                "properties": ["HOST_VISIBLE", "HOST_CACHED"]}]}},
                       "replay": {"objects": {"readback-buffer": [{"memory_type_index": 1,
                "properties": ["HOST_VISIBLE", "HOST_CACHED"]}]}}}}
        self.result = {"status": "FAIL", "checks": [{"check": "replay/readback-buffer", "status": "FAIL",
                      "expected": ["HOST_VISIBLE", "HOST_COHERENT", "HOST_CACHED"],
                      "observed": ["HOST_VISIBLE", "HOST_CACHED"]}]}
        (self.run / "observations.json").write_text(json.dumps(self.observed))
        (self.run / "result.json").write_text(json.dumps(self.result))
        (self.run / "input.gfxr").write_bytes(b"capture")

    def test_missing_case_is_an_error_instead_of_disappearing(self):
        rows = contract_report.collect(self.runs)
        self.assertEqual([row["result"]["status"] for row in rows], ["FAIL", "ERROR"])
        self.assertIn("0 passed, 1 failed, 1 error", contract_report.headline(rows))

    def test_html_escapes_text_and_shows_observations_and_expectations(self):
        rows = contract_report.collect(self.runs)
        page = contract_report.render(rows, self.runs, self.root / "report.html", 1)
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("HOST_VISIBLE + HOST_CACHED", page)
        self.assertIn("HOST_VISIBLE + HOST_COHERENT + HOST_CACHED", page)
        self.assertNotIn("type 3", page)
        self.assertIn("not_needed", page)
        self.assertIn("input.gfxr", page)

    def test_artifact_links_resolve_from_both_latest_and_archived_reports(self):
        rows = contract_report.collect(self.runs)
        for output in (self.root / "report.html", self.runs / "report.html"):
            links = Links()
            links.feed(contract_report.render(rows, self.runs, output, 1))
            artifacts = [href for href in links.hrefs if not href.startswith("#")]
            self.assertTrue(any("%20" in href for href in artifacts))
            for href in artifacts:
                self.assertTrue((output.parent / unquote(href)).is_file(), href)

    def test_incomplete_json_is_reported_as_an_error(self):
        (self.run / "result.json").write_text("{")
        self.assertEqual([row["result"]["status"] for row in contract_report.collect(self.runs)],
                         ["ERROR", "ERROR"])

    def test_index_failure_displays_properties(self):
        check = self.result["checks"][0]
        check["expected"] = {"memory-type-index": 3}
        check["observed"] = 1
        check["expected_properties"] = ["HOST_VISIBLE", "HOST_COHERENT", "HOST_CACHED"]
        check["observed_properties"] = ["HOST_VISIBLE", "HOST_CACHED"]
        row = {"result": self.result}
        self.assertEqual(contract_report.failure_details(row), [
            "replay/readback-buffer: HOST_VISIBLE + HOST_CACHED → expected HOST_VISIBLE + HOST_COHERENT + HOST_CACHED"])

    def test_equal_properties_keep_indices_visible(self):
        check = self.result["checks"][0]
        check["expected"] = {"memory-type-index": 3}
        check["observed"] = 1
        check["expected_properties"] = check["observed_properties"] = ["HOST_VISIBLE", "HOST_CACHED"]
        self.assertEqual(contract_report.failure_details({"result": self.result}), [
            "replay/readback-buffer: HOST_VISIBLE + HOST_CACHED (type 1) → expected HOST_VISIBLE + HOST_CACHED (type 3)"])

    def test_markdown_preserves_failures_missing_results_and_replay_input(self):
        summary = contract_report.render_markdown(contract_report.collect(self.runs), 1)
        self.assertIn("## Contract tests: 0 passed, 1 failed, 1 error", summary)
        self.assertIn("| memory/combined | ❌ FAIL | input.gfxr |", summary)
        self.assertIn("| memory/missing | ❌ ERROR | Not reached |", summary)
        self.assertIn("- replay/readback-buffer: HOST\\_VISIBLE + HOST\\_CACHED → expected", summary)
        self.assertIn("No complete case result", summary)
        self.assertNotIn("type 1", summary)

    def test_markdown_keeps_result_text_literal(self):
        rows = contract_report.collect(self.runs)
        rows[0]["case"] = "memory/[link](url)|<script>\nextra"
        rows[0]["result"]["error"] = "**failure** `code`"
        summary = contract_report.render_markdown(rows, 1)
        self.assertIn(r"memory/\[link\](url)\|&lt;script&gt; extra", summary)
        self.assertIn(r"\*\*failure\*\* \`code\`", summary)

    def test_markdown_does_not_hide_failure_after_passing_cases(self):
        rows = contract_report.collect(self.runs)[:1]
        rows[0]["result"] = {"status": "PASS", "checks": []}
        summary = contract_report.render_markdown(rows, 2)
        self.assertIn("1 passed, 0 failed", summary)
        self.assertIn("Suite command failed with exit code 2", summary)
        self.assertIn("✅ PASS", summary)


if __name__ == "__main__":
    unittest.main()
