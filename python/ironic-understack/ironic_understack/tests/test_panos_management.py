from unittest.mock import Mock

import pytest
from ironic.common import exception

from ironic_understack.drivers.panos_management import PanosManagement


@pytest.fixture
def task():
    task = Mock()
    task.node.uuid = "node-uuid"
    return task


def test_steps_are_registered():
    mgmt = PanosManagement()
    assert {s["step"]: s["priority"] for s in mgmt.get_clean_steps(Mock())} == {
        "reset_to_factory_defaults": 0,
        "clear_configuration": 0,
    }
    assert [s["step"] for s in mgmt.get_verify_steps(Mock())] == [
        "setup_initial_configuration"
    ]


def test_initial_configuration_does_not_block_enrollment(task):
    assert PanosManagement().setup_initial_configuration(task) is None


@pytest.mark.parametrize("step", ["reset_to_factory_defaults", "clear_configuration"])
def test_unimplemented_clean_steps_fail(task, step):
    with pytest.raises(exception.NodeCleaningFailure, match="not implemented"):
        getattr(PanosManagement(), step)(task)
