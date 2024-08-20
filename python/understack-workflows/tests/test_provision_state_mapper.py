import pytest

from understack_workflows.ironic.provision_state_mapper import ProvisioningStatusMapper


@pytest.mark.parametrize(
    "ironic_state,nautobot_state",
    [
        ("active", "Active"),
        ("deploying", "Provisioning"),
        ("wait call-back", None),
    ],
)
def test_translate(ironic_state, nautobot_state):
    result = ProvisioningStatusMapper.translate_to_nautobot(ironic_state)
    assert result == nautobot_state

def test_raises_on_unknown():
    with pytest.raises(ValueError):
        ProvisioningStatusMapper.translate_to_nautobot("blahblah")
