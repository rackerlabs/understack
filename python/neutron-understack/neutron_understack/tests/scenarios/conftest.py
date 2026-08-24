"""Scenario-test enforcement hooks.

Fails the collection if any test under the scenarios package is missing a
``@pytest.mark.scenario("<ID>")`` marker, so a scenario test cannot silently
escape the catalog↔marker coverage check in test_scenario_coverage.py.
"""

import pytest

# The coverage meta-test verifies the catalog itself and is not a scenario.
_EXEMPT_FILES = {"test_scenario_coverage.py"}


def pytest_collection_modifyitems(items):
    missing = []
    for item in items:
        path = str(getattr(item, "fspath", "")).replace("\\", "/")
        if "/tests/scenarios/" not in path:
            continue
        if path.rsplit("/", 1)[-1] in _EXEMPT_FILES:
            continue
        if item.get_closest_marker("scenario") is None:
            missing.append(item.nodeid)
    if missing:
        raise pytest.UsageError(
            "scenario tests missing an @pytest.mark.scenario('<ID>') marker:\n  "
            + "\n  ".join(missing)
        )
