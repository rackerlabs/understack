"""Enforce that the scenario catalog and the tests agree, in both directions.

- Every ``### <ID> — ...`` entry in SCENARIOS.md must be implemented by at least
  one test tagged ``@pytest.mark.scenario("<ID>")``.
- Every such marker must reference an ID that exists in SCENARIOS.md.

This is a static cross-check (it scans the catalog and the test sources), so it
holds regardless of which subset of tests a given run collects.
"""

import re
from pathlib import Path

from neutron_understack.tests.scenarios.catalog import catalog_ids

SCENARIOS_DIR = Path(__file__).parent
CATALOG = SCENARIOS_DIR / "SCENARIOS.md"

# Markers in test sources: @pytest.mark.scenario("BM-BIND-01").
_MARKER_ID_RE = re.compile(r"""\.scenario\(\s*["']([^"']+)["']""")


def _catalog_ids():
    return catalog_ids(CATALOG.read_text())


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
