from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from understack_workflows.main import create_port_group

NODE_UUID = "c5df377d-8cb0-44d7-b4c0-bdfa7d228bf0"
NODE_NAME = "Dell-5BFZMD4"


def _make_port(uuid, address, llc=None, name=None):
    return SimpleNamespace(
        id=uuid,
        address=address,
        local_link_connection=llc or {},
        name=name,
    )


# Ports based on the real device data - only two have local_link_connection
# with port_id populated.
PORTS = [
    _make_port(
        "cc0a4c29-0796-455c-b806-070ed124e839",
        "c8:4b:d6:f3:c8:80",
        llc={},
        name="Dell-5BFZMD4:NIC.Embedded.1-1-1",
    ),
    _make_port(
        "3024e6cd-82b1-42f5-9962-7686de039a50",
        "b4:83:51:24:e4:43",
        llc={},
        name="Dell-5BFZMD4:NIC.Integrated.1-2-1",
    ),
    _make_port(
        "ba699365-4763-4b6f-bf5a-fb7276dcb5a5",
        "b4:83:51:24:e4:44",
        llc={},
        name="Dell-5BFZMD4:NIC.Integrated.1-3-1",
    ),
    _make_port(
        "015b6cf7-ad9e-4a70-9113-76e8c8454f42",
        "b4:83:51:24:e4:45",
        llc={},
        name="Dell-5BFZMD4:NIC.Integrated.1-4-1",
    ),
    _make_port(
        "7aedc667-adaf-4cb0-9912-5dceddd2a375",
        "b4:83:51:24:58:b3",
        llc={
            "port_id": "Ethernet1/9",
            "switch_id": "ec:19:2e:c9:77:37",
            "switch_info": "g16-45-2.iad3.rackspace.net",
        },
        name="Dell-5BFZMD4:NIC.Slot.1-2-1",
    ),
    _make_port(
        "0de07302-2edc-4b92-9aaa-e504097784cc",
        "b4:83:51:24:58:b2",
        llc={},
        name="Dell-5BFZMD4:NIC.Slot.1-1-1",
    ),
    _make_port(
        "dd0bc58b-3be5-4d6c-8f97-8003aded65e4",
        "c8:4b:d6:f3:c8:81",
        llc={},
        name="Dell-5BFZMD4:NIC.Embedded.2-1-1",
    ),
    _make_port(
        "dac434df-7b24-455e-8570-ba6e1bbea244",
        "b4:83:51:24:e4:42",
        llc={
            "port_id": "Ethernet1/9",
            "switch_id": "ec:19:2e:c9:85:97",
            "switch_info": "g16-45-1.iad3.rackspace.net",
        },
        name="Dell-5BFZMD4:NIC.Integrated.1-1-1",
    ),
]


def _node(*, provision_state="manageable", name=NODE_NAME):
    return SimpleNamespace(
        id=NODE_UUID,
        name=name,
        provision_state=provision_state,
    )


def _mock_conn(mocker, *, node=None, ports=None, port_groups=None):
    conn = MagicMock()
    conn.baremetal.get_node.return_value = node
    conn.baremetal.ports.return_value = ports or []
    conn.baremetal.port_groups.return_value = port_groups or []
    conn.baremetal.create_port_group.return_value = SimpleNamespace(id="new-pg-uuid")
    mocker.patch(
        "understack_workflows.main.create_port_group.get_openstack_client",
        return_value=conn,
    )
    return conn


# --- dry-run reports correct port group name --------------------------------


def test_dry_run_reports_expected_port_group_name(mocker, caplog):
    """Given the real port data, dry-run should report the correct pg name.

    The primary port is selected by sorting eligible ports on
    (switch_info, port_id, address). With the two eligible ports:
      - g16-45-1... Ethernet1/9 (dac434df) -> sorts first
      - g16-45-2... Ethernet1/9 (7aedc667)

    port_channel suffix from "Ethernet1/9" -> "09"
    Expected name: Dell-5BFZMD4-port-channel109
    """
    _mock_conn(mocker, node=_node(), ports=PORTS)

    import logging

    with caplog.at_level(logging.INFO):
        create_port_group.create_port_group(NODE_UUID, dry_run=True)

    assert "Dell-5BFZMD4-port-channel109" in caplog.text
    assert "[dry-run]" in caplog.text


def test_dry_run_does_not_create_port_group(mocker, caplog):
    conn = _mock_conn(mocker, node=_node(), ports=PORTS)

    import logging

    with caplog.at_level(logging.INFO):
        create_port_group.create_port_group(NODE_UUID, dry_run=True)

    conn.baremetal.create_port_group.assert_not_called()
    conn.baremetal.update_port.assert_not_called()


# --- normal execution creates port group ------------------------------------


def test_creates_port_group_with_correct_name(mocker):
    conn = _mock_conn(mocker, node=_node(), ports=PORTS)

    create_port_group.create_port_group(NODE_UUID)

    conn.baremetal.create_port_group.assert_called_once()
    call_kwargs = conn.baremetal.create_port_group.call_args.kwargs
    assert call_kwargs["name"] == "Dell-5BFZMD4-port-channel109"
    assert call_kwargs["mode"] == "802.3ad"
    assert call_kwargs["node_id"] == NODE_UUID


def test_creates_port_group_with_primary_mac(mocker):
    """The MAC should come from the primary (first sorted) eligible port."""
    conn = _mock_conn(mocker, node=_node(), ports=PORTS)

    create_port_group.create_port_group(NODE_UUID)

    call_kwargs = conn.baremetal.create_port_group.call_args.kwargs
    # Primary is dac434df with MAC b4:83:51:24:e4:42
    assert call_kwargs["address"] == "b4:83:51:24:e4:42"


def test_assigns_eligible_ports_to_port_group(mocker):
    conn = _mock_conn(mocker, node=_node(), ports=PORTS)

    create_port_group.create_port_group(NODE_UUID)

    # Two eligible ports should be assigned
    assert conn.baremetal.update_port.call_count == 2
    updated_port_ids = {
        call.args[0] for call in conn.baremetal.update_port.call_args_list
    }
    assert updated_port_ids == {
        "7aedc667-adaf-4cb0-9912-5dceddd2a375",
        "dac434df-7b24-455e-8570-ba6e1bbea244",
    }


# --- error conditions -------------------------------------------------------


def test_exits_when_node_not_found(mocker):
    _mock_conn(mocker, node=None)

    with pytest.raises(SystemExit):
        create_port_group.create_port_group(NODE_UUID)


def test_exits_when_node_in_disallowed_state(mocker):
    _mock_conn(mocker, node=_node(provision_state="active"))

    with pytest.raises(SystemExit):
        create_port_group.create_port_group(NODE_UUID)


def test_exits_when_port_group_already_exists(mocker):
    existing_pg = SimpleNamespace(id="existing-pg")
    _mock_conn(mocker, node=_node(), ports=PORTS, port_groups=[existing_pg])

    with pytest.raises(SystemExit):
        create_port_group.create_port_group(NODE_UUID)


def test_exits_when_no_eligible_ports(mocker):
    # All ports have empty local_link_connection
    ports_no_llc = [
        _make_port("aaa", "00:11:22:33:44:55", llc={}),
        _make_port("bbb", "00:11:22:33:44:66", llc={}),
    ]
    _mock_conn(mocker, node=_node(), ports=ports_no_llc)

    with pytest.raises(SystemExit):
        create_port_group.create_port_group(NODE_UUID)


# --- parse_port_channel -----------------------------------------------------


def test_parse_port_channel_extracts_numeric_suffix():
    assert create_port_group.parse_port_channel("Ethernet1/9") == "09"
    assert create_port_group.parse_port_channel("Ethernet1/15") == "15"
    assert create_port_group.parse_port_channel("Ethernet1/1") == "01"


def test_parse_port_channel_exits_on_non_numeric(mocker):
    with pytest.raises(SystemExit):
        create_port_group.parse_port_channel("Ethernet1/foo")


# --- name vs uuid warning ---------------------------------------------------


def test_warns_when_name_provided_instead_of_uuid(mocker, caplog):
    _mock_conn(mocker, node=_node(), ports=PORTS)

    import logging

    with caplog.at_level(logging.WARNING):
        create_port_group.create_port_group("Dell-5BFZMD4")

    assert "not a UUID" in caplog.text
    assert "preferred" in caplog.text


def test_no_warning_when_uuid_provided(mocker, caplog):
    _mock_conn(mocker, node=_node(), ports=PORTS)

    import logging

    with caplog.at_level(logging.WARNING):
        create_port_group.create_port_group(NODE_UUID)

    assert "not a UUID" not in caplog.text
