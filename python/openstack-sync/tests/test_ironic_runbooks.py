"""Tests for the Ironic runbooks placeholder hook."""

from __future__ import annotations

import json
from unittest import mock

from openstack_sync.hooks import ironic_runbooks


def test_ironic_runbooks_hook_config(capsys):
    with mock.patch.object(
        ironic_runbooks.sys, "argv", ["ironic_runbooks.py", "--config"]
    ):
        assert ironic_runbooks.main() == 0

    config = json.loads(capsys.readouterr().out)
    assert config == ironic_runbooks.HOOK_CONFIG
    assert config["onStartup"] == 10


def test_ironic_runbooks_hook_run_is_noop():
    with mock.patch.object(ironic_runbooks.sys, "argv", ["ironic_runbooks.py"]):
        assert ironic_runbooks.main() == 0
