#!/usr/bin/env python3
"""Render a scenario traceability matrix from a scenario catalog + JUnit XML.

Reads a SCENARIOS.md catalog (``### <ID> — <title>`` headings) and, optionally,
a JUnit XML file produced by ``pytest --junitxml`` where each scenario test was
tagged with a ``scenario`` property (see the scenarios conftest.py). Emits a
markdown table mapping each catalogued scenario to its implementing test(s) and
last-run status, suitable for ``$GITHUB_STEP_SUMMARY`` or a docs page.

Reporting only: always exits 0. The catalog<->marker equivalence is enforced
separately by test_scenario_coverage.py.
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Catalog heading parsing is shared with the coverage meta-test so the format is
# defined once. Available because the script runs in the neutron-understack env.
from neutron_understack.tests.scenarios.catalog import parse_catalog as _parse_text

_STATUS = {
    "pass": "✅ pass",
    "fail": "❌ fail",
    "xfail": "⚠️ known bug (xfail)",
    "xpass": "🎉 fixed — remove xfail",
    "skipped": "⏭️ skipped",
    "missing": "❓ no test",
    "notrun": "· not run",
}


def parse_catalog(path):
    """Return ordered list of (id, title) from the catalog headings."""
    return _parse_text(Path(path).read_text())


def _testcase_status(testcase):
    failure = testcase.find("failure")
    if failure is not None or testcase.find("error") is not None:
        # A strict xfail that unexpectedly passes is a JUnit <failure> whose
        # message is "[XPASS(strict)] ...": the bug is fixed, remove the marker.
        if failure is not None and (failure.get("message") or "").startswith("[XPASS"):
            return "xpass"
        return "fail"
    skipped = testcase.find("skipped")
    if skipped is not None:
        return "xfail" if (skipped.get("type") or "").endswith("xfail") else "skipped"
    return "pass"


def parse_junit(path):
    """Return {scenario_id: [(test_name, status), ...]} from JUnit XML."""
    results = {}
    # Input is our own pytest JUnit output (trusted, CI-generated), not
    # untrusted external XML, so stdlib ElementTree is fine here.
    root = ET.parse(path).getroot()  # noqa: S314
    for testcase in root.iter("testcase"):
        sid = None
        for prop in testcase.iter("property"):
            if prop.get("name") == "scenario":
                sid = prop.get("value")
                break
        if sid is None:
            continue
        results.setdefault(sid, []).append(
            (testcase.get("name", "?"), _testcase_status(testcase))
        )
    return results


def render(catalog, results, junit_provided):
    lines = [
        "## ML2 scenario traceability",
        "",
        "| Scenario | Title | Test | Status |",
        "| --- | --- | --- | --- |",
    ]
    for sid, title in catalog:
        runs = results.get(sid)
        if not runs:
            status_key = "missing" if junit_provided else "notrun"
            lines.append(f"| `{sid}` | {title} | — | {_STATUS[status_key]} |")
            continue
        for test_name, status in runs:
            lines.append(f"| `{sid}` | {title} | `{test_name}` | {_STATUS[status]} |")
    # Surface any scenarios seen in JUnit that are not in the catalog.
    catalogued = {sid for sid, _ in catalog}
    for sid in sorted(set(results) - catalogued):
        for test_name, status in results[sid]:
            lines.append(
                f"| `{sid}` (uncataloged!) | — | `{test_name}` | {_STATUS[status]} |"
            )
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, help="path to SCENARIOS.md")
    parser.add_argument("--junit", help="path to pytest JUnit XML (optional)")
    args = parser.parse_args(argv)

    catalog = parse_catalog(args.catalog)
    results = parse_junit(args.junit) if args.junit else {}
    sys.stdout.write(render(catalog, results, junit_provided=bool(args.junit)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
