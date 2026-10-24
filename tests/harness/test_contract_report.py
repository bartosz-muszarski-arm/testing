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
                      "expected": {"memory-type-index": 3}, "observed": 1}]}
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
        self.assertIn("type 1: HOST_VISIBLE + HOST_CACHED", page)
        self.assertIn("type 3", page)
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


if __name__ == "__main__":
    unittest.main()
