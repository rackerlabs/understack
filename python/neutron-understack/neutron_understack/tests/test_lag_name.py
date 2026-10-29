import pytest

from neutron_understack.lag_name import InvalidLagAnchor
from neutron_understack.lag_name import lag_name


@pytest.mark.parametrize(
    ("port_id", "second", "expected"),
    [
        ("Eth1/17", False, "Po1170"),
        ("Eth1/17/2", False, "Po1172"),
        ("Eth1/96", True, "Po1965"),
        ("Eth1/102", False, "Po2020"),
        ("Eth1/102/3", True, "Po2028"),
        ("Ethernet1/1", False, "Po1010"),
        ("Eth1/308/4", True, "Po4089"),
    ],
)
def test_lag_name(port_id, second, expected):
    assert lag_name(port_id, second_switch=second) == expected


@pytest.mark.parametrize(
    "port_id",
    ["Eth2/1", "Eth1/0", "Eth1/309", "Eth1/1/0", "Eth1/1/5", "mgmt0", ""],
)
def test_rejects_invalid_anchor(port_id):
    with pytest.raises(InvalidLagAnchor):
        lag_name(port_id)
