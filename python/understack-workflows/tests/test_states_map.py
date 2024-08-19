import pytest

from understack_workflows.ironic.states_map import ProvisioningStatusMapper


def test_map_known_state():
    nautobot_status = ProvisioningStatusMapper.translate_to_nautobot(
        "enroll"
    )

    assert nautobot_status == "Planned"

def test_map_unknown_state():
    with pytest.raises(ValueError):
        ProvisioningStatusMapper.translate_to_nautobot("invalid state")

def test_map_known_but_not_mapped():
    result = ProvisioningStatusMapper.translate_to_nautobot("wait call-back")
    assert result is None
