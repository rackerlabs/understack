"""Enforce that the scenario catalog and the tests agree, in both directions.

- Every ``### <ID> — ...`` entry in SCENARIOS.md must be implemented by at least
  one test tagged ``@pytest.mark.scenario("<ID>")``.
- Every such marker must reference an ID that exists in SCENARIOS.md.

This is a static cross-check (it scans the catalog and the test sources), so it
holds regardless of which subset of tests a given run collects.
"""

import re
from pathlib import Path

SCENARIOS_DIR = Path(__file__).parent
CATALOG = SCENARIOS_DIR / "SCENARIOS.md"

# Catalog IDs are declared as headings: "### BM-BIND-01 — title".
_CATALOG_ID_RE = re.compile(r"^#{2,3}\s+([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\b")
# Markers in test sources: @pytest.mark.scenario("BM-BIND-01").
_MARKER_ID_RE = re.compile(r"""\.scenario\(\s*["']([^"']+)["']""")


def _catalog_ids():
    ids = []
    for line in CATALOG.read_text().splitlines():
        match = _CATALOG_ID_RE.match(line)
        if match:
            ids.append(match.group(1))
    return ids


def _marker_ids():
    ids = set()
    for path in SCENARIOS_DIR.glob("test_*.py"):
        if path.name == Path(__file__).name:
            continue
        ids.update(_MARKER_ID_RE.findall(path.read_text()))
    return ids


def test_catalog_has_no_duplicate_ids():
    ids = _catalog_ids()
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicates, f"duplicate scenario IDs in SCENARIOS.md: {duplicates}"


def test_every_catalogued_scenario_has_a_test():
    catalog = set(_catalog_ids())
    markers = _marker_ids()
    untested = sorted(catalog - markers)
    assert (
        not untested
    ), f"catalogued scenarios with no @pytest.mark.scenario test: {untested}"


def test_every_scenario_marker_is_catalogued():
    catalog = set(_catalog_ids())
    markers = _marker_ids()
    uncataloged = sorted(markers - catalog)
    assert (
        not uncataloged
    ), f"@pytest.mark.scenario IDs missing from SCENARIOS.md: {uncataloged}"
