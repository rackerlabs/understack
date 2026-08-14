"""Tests for the openstack-sync placeholder hook."""

from __future__ import annotations

import json
from unittest import mock

from openstack_sync.hooks import placeholder


def test_placeholder_hook_config(capsys):
    with mock.patch.object(placeholder.sys, "argv", ["placeholder.py", "--config"]):
        assert placeholder.main() == 0

    config = json.loads(capsys.readouterr().out)
    assert config == placeholder.HOOK_CONFIG
    assert config["onStartup"] == 10


def test_placeholder_hook_run_is_noop():
    with mock.patch.object(placeholder.sys, "argv", ["placeholder.py"]):
        assert placeholder.main() == 0
