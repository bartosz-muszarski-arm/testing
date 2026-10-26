#!/usr/bin/env python3
"""Summarize one contract-suite invocation without rerunning validation."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text())


def collect(runs):
    expected = [str(Path(line).with_suffix("")) for line in (runs / "cases.txt").read_text().splitlines()]
    found = {}
    for path in sorted(runs.glob("*/observations.json")):
        try:
            observed = read_json(path)
            result = read_json(path.parent / "result.json")
        except (OSError, ValueError):
            continue
        found.setdefault(observed["case"], []).append((path.parent, observed, result))
    rows = []
    for case in expected:
        matches = found.get(case, [])
        if len(matches) == 1:
            directory, observed, result = matches[0]
        else:
            directory, observed = None, {}
            result = {"status": "ERROR", "checks": [], "error":
                      "No complete case result; see setup log and suite output." if not matches else
                      "Multiple results for the same case in this invocation."}
        rows.append({"case": case, "directory": directory, "observations": observed, "result": result})
    return rows


def expectation(value, properties=None):
    if properties is not None:
        return " + ".join(properties)
    if isinstance(value, dict):
        return "type " + str(value["memory-type-index"])
    if isinstance(value, list):
        return " + ".join(value)
    return "—"


def selection(stage, name):
    objects = stage.get("objects", {}).get(name, [])
    if not objects:
        return "Missing observation"
    if len(objects) != 1:
        return "Ambiguous observation"
    obj = objects[0]
    index = obj.get("memory_type_index")
    if index is None:
        return "Unbound object"
    return " + ".join(obj.get("properties", []))


def failure_details(row):
    result = row["result"]
    details = [result[key] for key in ("error", "skip") if result.get(key)]
    for check in result["checks"]:
        if check["status"] == "PASS":
            continue
        detail = check["check"]
        if "expected" in check:
            actual = check.get("observed")
            expected = expectation(check["expected"], check.get("expected_properties"))
            if isinstance(check["expected"], dict):
                properties = check.get("observed_properties")
                if properties is not None:
                    actual = " + ".join(properties)
                    # Equal flags do not make distinct memory types interchangeable.
                    if properties == check.get("expected_properties") and check.get("observed") is not None:
                        actual += " (type " + str(check["observed"]) + ")"
                        expected += " (type " + str(check["expected"]["memory-type-index"]) + ")"
                elif actual is not None:
                    actual = "type " + str(actual)
            elif isinstance(actual, list):
                actual = " + ".join(actual)
            detail += ": " + str(actual) + " → expected " + expected
        elif check.get("reason"):
            detail += ": " + check["reason"]
        details.append(detail)
    return details


def headline(rows):
    counts = Counter(row["result"]["status"] for row in rows)
    parts = [f"{counts['PASS']} passed", f"{counts['FAIL']} failed"]
    parts.extend(f"{counts[status]} {label}" for status, label in
                 (("ERROR", "error" if counts["ERROR"] == 1 else "errors"),
                  ("INCONCLUSIVE", "inconclusive"), ("SKIP", "skipped")) if counts[status])
    return "Contract tests: " + ", ".join(parts)


def link(path, label, output):
    href = quote(os.path.relpath(path, output.parent), safe="/")
    return '<a href="' + escape(href, quote=True) + '">' + escape(label) + '</a>'


def markdown_text(value):
    """Keep result text literal inside Markdown tables and paragraphs."""
    text = escape(" ".join(str(value).splitlines()), quote=False)
    for character in ("\\", "`", "*", "_", "[", "]", "|"):
        text = text.replace(character, "\\" + character)
    return text


def render_markdown(rows, exit_status):
    lines = ["## " + headline(rows), ""]
    if not rows:
        lines.extend(("No contract cases were selected.", ""))
    if exit_status and all(row["result"]["status"] == "PASS" for row in rows):
        lines.extend((f"**Suite command failed with exit code {exit_status}.**", ""))
    icons = {"PASS": "✅", "FAIL": "❌", "ERROR": "❌", "SKIP": "⏭️", "INCONCLUSIVE": "⚠️"}
    lines.extend(("| Case | Result | Replay input |", "| --- | --- | --- |"))
    for row in rows:
        status = row["result"]["status"]
        replay_input = row["observations"].get("optimization", {}).get("replay_input", "Not reached")
        lines.append(f"| {markdown_text(row['case'])} | {icons.get(status, '⚠️')} {markdown_text(status)} | {markdown_text(replay_input)} |")
    for row in rows:
        details = failure_details(row)
        if details:
            lines.extend(("", "### " + markdown_text(row["case"]), ""))
            lines.extend("- " + markdown_text(detail) for detail in details)
    lines.extend(("", "Chameleon provides structural observations; GPU data correctness is not checked in these runs.", ""))
    return "\n".join(lines)


def render(rows, runs, output, exit_status):
    metadata = (runs / "metadata.txt").read_text() if (runs / "metadata.txt").is_file() else ""
    header = "<h1>" + escape(headline(rows)) + "</h1>"
    header += "<p>Generated " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") + "</p>"
    if metadata:
        header += "<pre>" + escape(metadata) + "</pre>"
    else:
        inputs = next((row["observations"].get("inputs", {}) for row in rows if row["observations"]), {})
        replay = inputs.get("replay", {})
        header += "<p>Replay tool: " + escape(replay.get("path", "Not available")) + "</p>"
        if replay.get("sha256"):
            header += "<p>SHA-256: <code>" + escape(replay["sha256"]) + "</code></p>"
    if exit_status and all(row["result"]["status"] == "PASS" for row in rows):
        header += '<p class="ERROR">Suite command failed with exit code ' + str(exit_status) + '.</p>'
    header += "<p>Chameleon provides structural observations. Data comparison is disabled in these runs.</p>"
    if (runs / "setup.log").is_file():
        header += "<p>" + link(runs / "setup.log", "Suite setup log", output) + "</p>"
    overview, sections = [], []
    for index, row in enumerate(rows):
        case, result, obs, directory = row["case"], row["result"], row["observations"], row["directory"]
        status = result["status"]
        optimization = obs.get("optimization", {})
        replay_input = optimization.get("replay_input", "Not reached")
        overview.append(f'<tr><td><a href="#case-{index}">{escape(case)}</a></td>'
                        f'<td class="{escape(status)}">{escape(status)}</td><td>{escape(replay_input)}</td></tr>')
        body = f'<section id="case-{index}"><h2>{escape(case)} <span class="{escape(status)}">{escape(status)}</span></h2>'
        body += "<p>" + escape(obs.get("description", "")) + "</p>"
        if optimization:
            body += "<p>Optimization: <strong>" + escape(optimization["status"]) + "</strong>. Replay input: <code>" + escape(replay_input) + "</code>.</p>"
            if optimization.get("reason"):
                body += "<p>" + escape(optimization["reason"]) + "</p>"
        details = failure_details(row)
        if details:
            body += "<ul>" + "".join("<li>" + escape(detail) + "</li>" for detail in details) + "</ul>"
        stages = obs.get("stages", {})
        replay_checks = {check["check"].split("/", 1)[1]: check for check in result["checks"]
                         if check["check"].startswith("replay/") and check["check"] != "replay/environment"}
        names = sorted(set(stages.get("capture", {}).get("objects", {})) |
                       set(stages.get("replay", {}).get("objects", {})) | set(replay_checks))
        if names:
            body += "<div class=scroll><table><thead><tr><th>Resource</th><th>Capture selection</th><th>Replay selection</th><th>Expected replay</th><th>Result</th></tr></thead><tbody>"
            for name in names:
                check = replay_checks.get(name, {})
                cells = (name, selection(stages.get("capture", {}), name),
                         selection(stages.get("replay", {}), name),
                         expectation(check.get("expected"), check.get("expected_properties")),
                         check.get("status", "INCONCLUSIVE"))
                body += "<tr>" + "".join("<td>" + escape(cell) + "</td>" for cell in cells) + "</tr>"
            body += "</tbody></table></div>"
        if directory:
            artifacts = [("observations.json", "Observed results"), ("result.json", "Validation"),
                         ("description.yaml", "Case definition"), ("workload.cpp", "Workload"),
                         ("commands.jsonl", "Commands"), ("compile.log", "Compile log"),
                         ("capture.log", "Capture log"), ("optimize.log", "Optimizer log"),
                         ("replay.log", "Replay log"), ("input.gfxr", "Original trace"),
                         ("optimized.gfxr", "Optimized trace")]
            artifacts += [(p.name, "Raw " + p.name) for stage in ("capture", "replay")
                          for p in sorted(directory.glob(stage + "_*.json"))]
            body += "<p class=links>" + " · ".join(link(directory / path, label, output)
                       for path, label in artifacts if (directory / path).is_file()) + "</p>"
        sections.append(body + "</section>")
    return '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Contract test report</title>
<style>
body{font:16px/1.5 system-ui,sans-serif;color:#20252b;background:#fafbfc;max-width:1200px;margin:32px auto;padding:0 20px}
h1{font-size:1.8rem}h2{font-size:1.2rem}a{color:#175ca4}pre,code{overflow-wrap:anywhere;white-space:pre-wrap;font-size:.85rem}
table{border-collapse:collapse;width:100%;background:white}td,th{padding:10px 12px;text-align:left;border:1px solid #dbe0e5;vertical-align:top;overflow-wrap:anywhere}th{background:#eef1f5}
section{margin:32px 0;padding:20px;background:white;border:1px solid #dbe0e5;border-radius:6px}.scroll{overflow-x:auto}.links{font-size:.85rem}
.PASS{color:#17663a;font-weight:700}.FAIL,.ERROR{color:#a11d28;font-weight:700}.SKIP,.INCONCLUSIVE{color:#835600;font-weight:700}
</style><body>''' + header + "<table><thead><tr><th>Case</th><th>Result</th><th>Replay input</th></tr></thead><tbody>" + "".join(overview) + "</tbody></table>" + "".join(sections) + "</body></html>\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exit-status", type=int, default=0)
    args = parser.parse_args()
    runs, output = args.runs.resolve(), args.output.resolve()
    rows = collect(runs)
    summary = [headline(rows), ""]
    for row in rows:
        summary.append(f"{row['result']['status']:<12} {row['case']}")
        summary.extend("    " + detail for detail in failure_details(row))
    if not rows:
        summary.append("No contract cases were selected.")
    report_path = os.path.relpath(output, ROOT)
    summary.extend(("", "Report: " + report_path))
    text = "\n".join(summary) + "\n"
    output.write_text(render(rows, runs, output, args.exit_status))
    (runs / "report.html").write_text(render(rows, runs, runs / "report.html", args.exit_status))
    output.with_suffix(".txt").write_text(text)
    (runs / "summary.txt").write_text(text)
    markdown = render_markdown(rows, args.exit_status)
    output.with_suffix(".md").write_text(markdown)
    (runs / "summary.md").write_text(markdown)
    print("\n" + text, flush=True)


if __name__ == "__main__":
    main()
