"""Single source of truth for parsing the SCENARIOS.md catalog.

Both the coverage meta-test (test_scenario_coverage.py) and the CI report
(scripts/scenario-report.py) parse scenario IDs from the catalog headings; they
import from here so the heading format is defined once and cannot diverge.
"""

import re

#: Catalog IDs are declared as headings: "### <ID> — <title>" (title optional).
_CATALOG_RE = re.compile(
    r"^#{2,3}\s+([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)(?:\s*[—-]\s*(.*))?$"
)


def parse_catalog(text):
    """Return an ordered list of ``(scenario_id, title)`` from the catalog."""
    entries = []
    for line in text.splitlines():
        match = _CATALOG_RE.match(line)
        if match:
            entries.append((match.group(1), (match.group(2) or "").strip()))
    return entries


def catalog_ids(text):
    """Return an ordered list of catalogued scenario IDs."""
    return [scenario_id for scenario_id, _ in parse_catalog(text)]
