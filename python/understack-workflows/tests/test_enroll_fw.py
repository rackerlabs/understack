from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from ironicclient.common.apiclient import exceptions as ironic_exceptions

from understack_workflows.main import enroll_fw

BASE_ARGS: dict[str, Any] = {
    "name": "PA1410-026701008071",
    "physical_network": "f20-1-network",
    "resource_class": "pa1410",
}

FW_FIELDS: dict[str, Any] = {
    "management_ip": "10.15.149.46",
    "management_switch": "n11-22-1d.dfw3",
    "management_switch_port": "Ethernet1/24",
    "mate_serial": "026701010045",
}


def _node(
    *,
    driver: str = "panos",
    resource_class: str = "pa1410",
    provision_state: str = "active",
    driver_info: dict | None = None,
    extra: dict | None = None,
):
    return SimpleNamespace(
        uuid="node-uuid",
        name=BASE_ARGS["name"],
        driver=driver,
        resource_class=resource_class,
        provision_state=provision_state,
        driver_info=driver_info or {},
        extra=extra or {},
    )


def _mock_client(mocker, *, node=None, node_ports=None):
    client = MagicMock()
    if node is None:
        client.get_node.side_effect = ironic_exceptions.NotFound()
    else:
        client.get_node.return_value = node
    client.list_ports.return_value = node_ports or []
    mocker.patch.object(enroll_fw, "IronicClient", return_value=client)
    return client


def _patch_paths(update_node_call) -> dict[str, Any]:
    (_uuid, patch), _ = update_node_call
    return {op["path"]: op["value"] for op in patch}


def _mock_enroll(mocker, *, created=True):
    """Mock creating or reusing the node, and the inspection that follows it."""
    node = _node(provision_state="enroll" if created else "available")
    mocker.patch.object(enroll_fw.netdev_reconciler, "make_manageable")
    return SimpleNamespace(
        node=node,
        create=mocker.patch.object(
            enroll_fw.netdev_reconciler,
            "find_or_create_netdev_node",
            return_value=(node, created),
        ),
        metadata=mocker.patch.object(
            enroll_fw.netdev_reconciler, "update_node_metadata"
        ),
        traits=mocker.patch.object(enroll_fw.netdev_reconciler, "update_node_traits"),
        inspect=mocker.patch.object(enroll_fw, "_inspect_and_provide"),
    )


# --- enrollment path (new / re-enrollable node) -----------------------------


def test_enroll_fw_creates_the_node_with_its_metadata(mocker):
    client = _mock_client(mocker, node=None)  # not found -> new node
    enroll = _mock_enroll(mocker)

    node_uuid = enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    assert node_uuid == "node-uuid"
    enroll.create.assert_called_once_with(
        client=client,
        name="PA1410-026701008071",
        resource_class="pa1410",
        driver="panos",
        driver_info={
            "management_ip": "10.15.149.46",
            "management_switch": "n11-22-1d.dfw3",
            "management_switch_port": "Ethernet1/24",
        },
        extra={"mate_serial": "026701010045"},
        properties={},
    )
    enroll.metadata.assert_not_called()  # a new node already has it
    enroll.traits.assert_called_once_with(
        client=client,
        node=enroll.node,
        traits={"CUSTOM_PRIMARY": False, "CUSTOM_SECONDARY": False},
    )
    enroll.inspect.assert_called_once_with(client, "node-uuid", "f20-1-network", "")


@pytest.mark.parametrize(
    ("ha_role", "traits"),
    [
        ("primary", {"CUSTOM_PRIMARY": True, "CUSTOM_SECONDARY": False}),
        ("secondary", {"CUSTOM_PRIMARY": False, "CUSTOM_SECONDARY": True}),
    ],
)
def test_enroll_fw_sets_the_ha_role_trait(mocker, ha_role, traits):
    _mock_client(mocker, node=None)
    enroll = _mock_enroll(mocker)

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS, ha_role=ha_role)

    assert enroll.traits.call_args.kwargs["traits"] == traits


def test_enroll_fw_records_the_cmdb_id_in_extra(mocker):
    _mock_client(mocker, node=None)
    enroll = _mock_enroll(mocker)

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS, external_cmdb_id=12345)

    assert enroll.create.call_args.kwargs["extra"] == {
        "mate_serial": "026701010045",
        "external_cmdb_id": 12345,
    }


def test_enroll_fw_requires_a_mate_serial_with_an_ha_role(mocker):
    client = mocker.patch.object(enroll_fw, "IronicClient")
    fields = {**FW_FIELDS, "mate_serial": ""}

    with pytest.raises(ValueError, match="--mate-serial with --ha-role"):
        enroll_fw.enroll_fw(**BASE_ARGS, **fields, ha_role="primary")

    client.assert_not_called()


def test_enroll_fw_optional_fw_fields_can_be_omitted(mocker):
    # management_switch/port are required; management_ip, mate_serial and
    # external_cmdb_id are optional and are simply absent from the metadata.
    _mock_client(mocker, node=None)
    enroll = _mock_enroll(mocker)

    enroll_fw.enroll_fw(
        **BASE_ARGS,
        management_switch="n11-22-1d.dfw3",
        management_switch_port="Ethernet1/24",
    )

    _, kwargs = enroll.create.call_args
    assert kwargs["driver_info"] == {
        "management_switch": "n11-22-1d.dfw3",
        "management_switch_port": "Ethernet1/24",
    }
    assert kwargs["extra"] == {}


def test_enroll_fw_creates_the_node_with_an_explicit_legacy_driver(mocker):
    _mock_client(mocker, node=None)
    enroll = _mock_enroll(mocker)

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS, driver="netdev")

    assert enroll.create.call_args.kwargs["driver"] == "netdev"


@pytest.mark.parametrize("driver", ["", "   "])
def test_enroll_fw_rejects_blank_driver_before_ironic_calls(mocker, driver):
    client = mocker.patch.object(enroll_fw, "IronicClient")
    create = mocker.patch.object(
        enroll_fw.netdev_reconciler, "find_or_create_netdev_node"
    )

    with pytest.raises(ValueError, match="non-empty --driver"):
        enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS, driver=driver)

    client.assert_not_called()
    create.assert_not_called()


def test_existing_non_active_node_is_updated_and_inspected_again(mocker):
    # A found-but-available node is re-enrollable: its metadata is updated and
    # it is inspected again, rather than treated as in-service.
    client = _mock_client(mocker, node=_node(provision_state="available"))
    enroll = _mock_enroll(mocker, created=False)

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    enroll.metadata.assert_called_once()
    enroll.inspect.assert_called_once_with(client, "node-uuid", "f20-1-network", "")


def test_enroll_fw_rejects_generic_and_empty_resource_class(mocker):
    create = mocker.patch.object(
        enroll_fw.netdev_reconciler, "find_or_create_netdev_node"
    )

    for bad in ("", "   ", "generic", "GENERIC", " generic "):
        args = {**BASE_ARGS, "resource_class": bad}
        with pytest.raises(ValueError, match="purpose-made"):
            enroll_fw.enroll_fw(**args, **FW_FIELDS)

    # Rejected before the engine (or any Ironic call) is ever invoked.
    create.assert_not_called()


def test_enroll_fw_normalizes_resource_class_whitespace(mocker):
    _mock_client(mocker, node=None)
    enroll = _mock_enroll(mocker)
    args = {**BASE_ARGS, "resource_class": "  pa1410  "}

    enroll_fw.enroll_fw(**args, **FW_FIELDS)

    assert enroll.create.call_args.kwargs["resource_class"] == "pa1410"


def test_enroll_fw_requires_management_switch(mocker):
    create = mocker.patch.object(
        enroll_fw.netdev_reconciler, "find_or_create_netdev_node"
    )

    for bad in ("", "   "):
        args = {**BASE_ARGS, **FW_FIELDS, "management_switch": bad}
        with pytest.raises(ValueError, match="management-switch"):
            enroll_fw.enroll_fw(**args)

    # Rejected before the engine (or any Ironic call) is ever invoked.
    create.assert_not_called()


def test_enroll_fw_requires_management_switch_port(mocker):
    create = mocker.patch.object(
        enroll_fw.netdev_reconciler, "find_or_create_netdev_node"
    )

    for bad in ("", "   "):
        args = {**BASE_ARGS, **FW_FIELDS, "management_switch_port": bad}
        with pytest.raises(ValueError, match="management-switch-port"):
            enroll_fw.enroll_fw(**args)

    create.assert_not_called()


# --- in-service (active) node: metadata-only in place -----------------------


def test_active_node_updates_metadata_only(mocker):
    client = _mock_client(mocker, node=_node())
    create = mocker.patch.object(
        enroll_fw.netdev_reconciler, "find_or_create_netdev_node"
    )

    node_uuid = enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    assert node_uuid == "node-uuid"
    create.assert_not_called()
    client.list_ports.assert_not_called()  # a live firewall's ports are left alone
    client.update_port.assert_not_called()
    client.update_node.assert_called_once()
    paths = _patch_paths(client.update_node.call_args)
    assert paths["/driver_info/management_ip"] == "10.15.149.46"
    assert paths["/extra/mate_serial"] == "026701010045"


def test_active_node_records_external_cmdb_id(mocker):
    client = _mock_client(mocker, node=_node())

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS, external_cmdb_id=12345)

    paths = _patch_paths(client.update_node.call_args)
    assert paths["/extra/external_cmdb_id"] == 12345


def test_active_node_noop_when_metadata_already_matches(mocker):
    node = _node(
        driver_info={
            "management_ip": "10.15.149.46",
            "management_switch": "n11-22-1d.dfw3",
            "management_switch_port": "Ethernet1/24",
        },
        extra={"mate_serial": "026701010045"},
    )
    client = _mock_client(mocker, node=node)

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    client.update_node.assert_not_called()


@pytest.mark.parametrize("driver", ["ipmi", "netdev"])
def test_active_node_rejects_different_driver(mocker, driver):
    client = _mock_client(mocker, node=_node(driver=driver))

    with pytest.raises(RuntimeError, match="refusing to enroll it as 'panos'"):
        enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    client.update_node.assert_not_called()


def test_active_legacy_node_updates_metadata_with_explicit_matching_driver(mocker):
    client = _mock_client(mocker, node=_node(driver="netdev"))
    create = mocker.patch.object(
        enroll_fw.netdev_reconciler, "find_or_create_netdev_node"
    )

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS, driver="netdev")

    create.assert_not_called()
    client.update_node.assert_called_once()
    paths = _patch_paths(client.update_node.call_args)
    assert paths["/driver_info/management_ip"] == "10.15.149.46"
    assert "/driver" not in paths
    client.set_node_provision_state.assert_not_called()


def test_active_node_rejects_resource_class_change(mocker):
    client = _mock_client(mocker, node=_node(resource_class="pa5410"))

    with pytest.raises(RuntimeError, match="resource_class"):
        enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    client.update_node.assert_not_called()


def test_active_node_with_the_same_ha_role_gets_metadata_updates(mocker):
    client = _mock_client(mocker, node=_node())
    client.get_node_traits.return_value = ["CUSTOM_PRIMARY", "CUSTOM_OTHER"]

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS, ha_role="primary")

    client.update_node.assert_called_once()


@pytest.mark.parametrize(
    ("current", "ha_role"),
    [(["CUSTOM_PRIMARY"], "secondary"), ([], "primary"), (["CUSTOM_PRIMARY"], "")],
    ids=["primary-to-secondary", "add-role", "drop-role"],
)
def test_active_node_rejects_an_ha_role_change(mocker, current, ha_role):
    client = _mock_client(mocker, node=_node())
    client.get_node_traits.return_value = current

    with pytest.raises(RuntimeError, match="HA traits"):
        enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS, ha_role=ha_role)

    client.update_node.assert_not_called()


# --- argument parsing -------------------------------------------------------


@pytest.mark.parametrize(
    ("driver_args", "expected"), [([], "panos"), (["--driver", "netdev"], "netdev")]
)
def test_main_passes_default_or_explicit_driver(mocker, driver_args, expected):
    engine = mocker.patch.object(enroll_fw, "enroll_fw")
    mocker.patch.object(enroll_fw.helpers, "setup_logger")
    mocker.patch(
        "sys.argv",
        [
            "enroll-fw",
            "--name",
            "fw1",
            "--physical-network",
            "net",
            "--resource-class",
            "pa1410",
            "--management-switch",
            "switch1",
            "--management-switch-port",
            "eth1",
            *driver_args,
        ],
    )

    enroll_fw.main()

    assert engine.call_args.kwargs["driver"] == expected


def test_main_emits_node_uuid_only_after_success(mocker, tmp_path):
    output = tmp_path / "node-uuid"
    mocker.patch.object(enroll_fw.helpers, "setup_logger")
    mocker.patch(
        "sys.argv",
        [
            "enroll-fw",
            "--name",
            "fw1",
            "--physical-network",
            "net",
            "--resource-class",
            "pa1410",
            "--management-switch",
            "switch1",
            "--management-switch-port",
            "eth1",
            "--node-uuid-output",
            str(output),
        ],
    )
    engine = mocker.patch.object(enroll_fw, "enroll_fw", return_value="node-123")

    enroll_fw.main()

    assert output.read_text() == "node-123\n"
    output.unlink()
    engine.side_effect = RuntimeError("enrollment failed")
    with pytest.raises(RuntimeError, match="enrollment failed"):
        enroll_fw.main()
    assert not output.exists()


def test_argument_parser_requires_resource_class():
    parser = enroll_fw.argument_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--name",
                "fw1",
                "--physical-network",
                "net",
                "--management-switch",
                "switch1",
                "--management-switch-port",
                "eth1",
            ]
        )


def test_argument_parser_requires_management_switch_and_port():
    # Everything except the management switch/port -> argparse rejects it.
    parser = enroll_fw.argument_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--name",
                "fw1",
                "--physical-network",
                "net",
                "--resource-class",
                "pa1410",
            ]
        )


def test_argument_parser_rejects_a_ports_list():
    # Inspection finds the ports over LLDP; a typed list is never taken.
    parser = enroll_fw.argument_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--name",
                "fw1",
                "--physical-network",
                "net",
                "--resource-class",
                "pa1410",
                "--management-switch",
                "switch1",
                "--management-switch-port",
                "eth1",
                "--ports",
                "[]",
            ]
        )


# --- enrollment (inspection finds and labels the ports) ---------------------


def _enroll_and_inspect(mocker, categories, physnet=None):
    """Mock a new node whose inspection leaves ports with these categories."""
    client = _mock_client(
        mocker,
        node_ports=[
            SimpleNamespace(
                uuid=f"port-{i}",
                name=f"fw:ethernet1/{i}",
                address=f"60:15:2b:00:00:{i:02x}",
                category=c,
                physical_network=physnet,
            )
            for i, c in enumerate(categories, start=1)
        ],
    )
    node = _node(provision_state="enroll")
    client.get_node.side_effect = [ironic_exceptions.NotFound(), node]
    transition = mocker.patch.object(enroll_fw.ironic_node, "transition")
    mocker.patch.object(
        enroll_fw.netdev_reconciler,
        "find_or_create_netdev_node",
        return_value=(node, True),
    )
    return client, transition


def _steps(transition):
    return [call.kwargs["target_state"] for call in transition.call_args_list]


def _physnet_updates(client):
    return {call.args[0]: call.args[1] for call in client.update_port.call_args_list}


def test_enroll_inspects_before_providing(mocker):
    client, transition = _enroll_and_inspect(mocker, ["outside", "inside", None])

    node_uuid = enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    assert node_uuid == "node-uuid"
    assert _steps(transition) == ["manage", "inspect", "provide"]
    # Only the role ports get the physical network.
    patch = [{"op": "add", "path": "/physical_network", "value": "f20-1-network"}]
    assert _physnet_updates(client) == {"port-1": patch, "port-2": patch}


def test_enroll_keeps_a_matching_physical_network(mocker):
    client, transition = _enroll_and_inspect(
        mocker, ["outside", "inside"], physnet="f20-1-network"
    )

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    client.update_port.assert_not_called()
    assert _steps(transition) == ["manage", "inspect", "provide"]


def test_enroll_is_not_provided_without_both_roles(mocker):
    client, transition = _enroll_and_inspect(mocker, ["outside", None])

    with pytest.raises(RuntimeError, match="left 0 inside ports, expected one"):
        enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    assert _steps(transition) == ["manage", "inspect"]
    client.update_port.assert_not_called()


def test_enroll_fw_is_not_provided_with_two_ports_in_one_role(mocker):
    client, transition = _enroll_and_inspect(mocker, ["outside", "outside", "inside"])

    with pytest.raises(RuntimeError, match="left 2 outside ports, expected one"):
        enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS)

    assert _steps(transition) == ["manage", "inspect"]
    client.update_port.assert_not_called()


def test_enroll_marks_a_secondary_before_inspecting(mocker):
    client, transition = _enroll_and_inspect(mocker, ["outside", "inside"])
    client.get_node.side_effect = [ironic_exceptions.NotFound(), _node(), _node()]
    calls = mocker.Mock()
    calls.attach_mock(client.add_node_trait, "add_node_trait")
    calls.attach_mock(transition, "transition")

    enroll_fw.enroll_fw(**BASE_ARGS, **FW_FIELDS, ha_role="secondary")

    client.add_node_trait.assert_called_once_with("node-uuid", "CUSTOM_SECONDARY")
    steps = [kwargs.get("target_state", name) for name, _, kwargs in calls.mock_calls]
    # Not provided: inspection has not confirmed the HA pair.
    assert steps == ["manage", "add_node_trait", "inspect"]


def test_enroll_fw_requires_a_physical_network(mocker):
    client = _mock_client(mocker)

    with pytest.raises(ValueError, match="--physical-network"):
        enroll_fw.enroll_fw(**{**BASE_ARGS, "physical_network": " "}, **FW_FIELDS)

    client.get_node.assert_not_called()


def test_argument_parser_requires_physical_network():
    parser = enroll_fw.argument_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--name",
                "fw1",
                "--resource-class",
                "pa1410",
                "--management-switch",
                "switch1",
                "--management-switch-port",
                "eth1",
            ]
        )


def test_argument_parser_rejects_an_unknown_ha_role():
    parser = enroll_fw.argument_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--name",
                "fw1",
                "--physical-network",
                "net",
                "--resource-class",
                "pa1410",
                "--management-switch",
                "switch1",
                "--management-switch-port",
                "eth1",
                "--ha-role",
                "standby",
            ]
        )


# --- HA pair: promotion once inspection confirms the pair -------------------

SERIAL = "026701008071"
MATE_SERIAL = FW_FIELDS["mate_serial"]
PHYSNET = BASE_ARGS["physical_network"]
INTERFACES = ("ethernet1/19", "ethernet1/20")


def _ha_node(uuid, *, serial, mate_serial, **fields):
    extra = {"serial": serial, "mate_serial": mate_serial}
    if "ha_operational" in fields:
        extra["ha_operational"] = fields.pop("ha_operational")
    return SimpleNamespace(
        **{
            "uuid": uuid,
            "name": uuid,
            "driver": "panos",
            "resource_class": "pa1410",
            "owner": "infra-project",
            "maintenance": False,
            "provision_state": "manageable",
            "parent_node": None,
            "driver_info": {},
            "extra": extra,
            **fields,
        }
    )


def _role_ports(node_uuid, *, physnet=PHYSNET, interfaces=INTERFACES):
    return [
        SimpleNamespace(
            uuid=f"{node_uuid}-{role}",
            name=f"{node_uuid}:{interface}",
            address=f"60:15:2b:00:00:0{i}",
            category=role,
            physical_network=physnet,
            extra={"bios_name": interface},
        )
        for i, (role, interface) in enumerate(
            zip(("outside", "inside"), interfaces, strict=True), start=1
        )
    ]


class FakeIronic:
    """The few IronicClient calls promotion makes, over in-memory nodes."""

    def __init__(self, nodes, traits, ports=None):
        self.nodes = {node.uuid: node for node in nodes}
        self.traits = traits
        self.ports = ports or {uuid: _role_ports(uuid) for uuid in self.nodes}
        self.updates = []

    def get_node(self, ident):
        if ident not in self.nodes:
            raise ironic_exceptions.NotFound()
        return self.nodes[ident]

    def list_nodes(self, **filters):
        assert filters == {"driver": "panos", "detail": True, "include_children": True}
        return list(self.nodes.values())

    def list_child_nodes(self, parent_uuid):
        return [n for n in self.nodes.values() if n.parent_node == parent_uuid]

    def get_node_traits(self, uuid):
        return self.traits.get(uuid, [])

    def list_ports(self, uuid):
        return self.ports.get(uuid, [])

    def update_node(self, uuid, ops):
        self.updates.append((uuid, ops))
        node = self.nodes[uuid]
        for op in ops:
            field, *key = op["path"].strip("/").split("/")
            if key:
                getattr(node, field)[key[0]] = op["value"]
            else:
                setattr(node, field, op.get("value"))


def _pair(this_role, *, this=None, mate=None, traits=None, ports=None):
    """This node ("fw-this", confirmed) and its mate ("fw-mate", not yet)."""
    mate_role = "secondary" if this_role == "primary" else "primary"
    this_node = _ha_node(
        "fw-this",
        serial=SERIAL,
        mate_serial=MATE_SERIAL,
        **{"ha_operational": True, **(this or {})},
    )
    mate_node = _ha_node(
        "fw-mate",
        serial=MATE_SERIAL,
        mate_serial=SERIAL,
        **{"ha_operational": False, **(mate or {})},
    )
    traits = traits or {
        "fw-this": [enroll_fw.firewall.HA_ROLE_TRAITS[this_role]],
        "fw-mate": [enroll_fw.firewall.HA_ROLE_TRAITS[mate_role]],
    }
    return FakeIronic([this_node, mate_node], traits, ports)


def _promote(mocker, ironic, ha_role):
    transition = mocker.patch.object(enroll_fw.ironic_node, "transition")
    enroll_fw._inspect_and_provide(ironic, "fw-this", PHYSNET, ha_role)
    return [(c.args[0].uuid, c.kwargs["target_state"]) for c in transition.mock_calls]


LINK = [
    {"op": "add", "path": "/parent_node", "value": "fw-primary"},
    {"op": "add", "path": "/driver_info/has_dedicated_power_supply", "value": True},
]
SET_HA_OPERATIONAL = [{"op": "add", "path": "/extra/ha_operational", "value": True}]


def _link_to(primary):
    return [{**LINK[0], "value": primary}, LINK[1]]


def test_ha_unit_waits_for_its_mate_until_the_pair_is_confirmed(mocker):
    ironic = _pair("primary", this={"ha_operational": False})

    steps = _promote(mocker, ironic, "primary")

    assert steps == [("fw-this", "inspect")]
    assert ironic.updates == []


@pytest.mark.parametrize(
    ("this_role", "secondary", "primary"),
    [("primary", "fw-mate", "fw-this"), ("secondary", "fw-this", "fw-mate")],
)
def test_ha_pair_is_linked_then_both_are_provided(
    mocker, this_role, secondary, primary
):
    ironic = _pair(this_role)

    steps = _promote(mocker, ironic, this_role)

    # One update links the secondary with power coupling off, before provide.
    assert ironic.updates == [
        (secondary, _link_to(primary)),
        ("fw-mate", SET_HA_OPERATIONAL),
    ]
    assert steps == [
        ("fw-this", "inspect"),
        ("fw-mate", "provide"),
        ("fw-this", "provide"),
    ]


def test_ha_promotion_rerun_on_a_linked_pair_writes_nothing(mocker):
    ironic = _pair(
        "primary",
        mate={
            "provision_state": "available",
            "parent_node": "fw-this",
            "driver_info": {"has_dedicated_power_supply": True},
            "ha_operational": True,
        },
    )

    steps = _promote(mocker, ironic, "primary")

    assert ironic.updates == []
    assert steps == [("fw-this", "inspect"), ("fw-this", "provide")]


def test_ha_promotion_with_an_active_mate_only_updates_its_metadata(mocker):
    # A replacement secondary next to the primary that carries a router.
    ironic = _pair("secondary", mate={"provision_state": "active"})

    steps = _promote(mocker, ironic, "secondary")

    assert ironic.updates == [
        ("fw-this", _link_to("fw-mate")),
        ("fw-mate", SET_HA_OPERATIONAL),
    ]
    assert steps == [("fw-this", "inspect"), ("fw-this", "provide")]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"mate": {"extra": {"serial": MATE_SERIAL}}}, "the mate's mate_serial"),
        ({"mate": {"resource_class": "pa3410"}}, "resource_class is"),
        ({"mate": {"owner": "other-project"}}, "owner is"),
        ({"mate": {"maintenance": True}}, "the mate is in maintenance"),
        ({"this": {"maintenance": True}}, "this node is in maintenance"),
        ({"mate": {"provision_state": "inspect wait"}}, "the mate is inspect wait"),
        (
            {"traits": {"fw-this": ["CUSTOM_PRIMARY"], "fw-mate": ["CUSTOM_PRIMARY"]}},
            "expected CUSTOM_SECONDARY only",
        ),
        (
            {"ports": {"fw-this": _role_ports("fw-this"), "fw-mate": []}},
            "the mate has 0 outside ports",
        ),
        (
            {
                "ports": {
                    "fw-this": _role_ports("fw-this"),
                    "fw-mate": _role_ports("fw-mate", physnet="f20-2-network"),
                }
            },
            "the mate's outside port is on 'f20-2-network'",
        ),
        (
            {
                "ports": {
                    "fw-this": _role_ports("fw-this"),
                    "fw-mate": _role_ports(
                        "fw-mate", interfaces=("ethernet1/1", "ethernet1/20")
                    ),
                }
            },
            "outside is 'ethernet1/19' here but 'ethernet1/1' on the mate",
        ),
    ],
    ids=[
        "mate-serial",
        "resource-class",
        "owner",
        "mate-maintenance",
        "maintenance",
        "mate-busy",
        "same-role",
        "mate-ports",
        "physnet",
        "interface",
    ],
)
def test_ha_promotion_refuses_a_mismatched_pair(mocker, change, message):
    ironic = _pair("primary", **change)

    with pytest.raises(RuntimeError, match=message):
        _promote(mocker, ironic, "primary")

    assert ironic.updates == []


@pytest.mark.parametrize("copies", [0, 2])
def test_ha_promotion_needs_exactly_one_mate(mocker, copies):
    ironic = _pair("primary")
    del ironic.nodes["fw-mate"]
    for i in range(copies):
        ironic.nodes[f"fw-mate-{i}"] = _ha_node(
            f"fw-mate-{i}", serial=MATE_SERIAL, mate_serial=SERIAL
        )

    with pytest.raises(RuntimeError, match=f"Found {copies} panos nodes"):
        _promote(mocker, ironic, "primary")

    assert ironic.updates == []


def test_ha_promotion_needs_a_serial(mocker):
    ironic = _pair("primary")
    del ironic.nodes["fw-this"].extra["serial"]

    with pytest.raises(RuntimeError, match=r"Has no extra\.serial"):
        _promote(mocker, ironic, "primary")


def test_ha_promotion_refuses_a_secondary_linked_to_another_live_primary(mocker):
    ironic = _pair("primary", mate={"parent_node": "fw-old"})
    ironic.nodes["fw-old"] = _ha_node("fw-old", serial="999", mate_serial="000")

    with pytest.raises(RuntimeError, match="linked to another primary fw-old"):
        _promote(mocker, ironic, "primary")

    assert ironic.updates == []


def test_ha_promotion_refuses_a_primary_with_another_child(mocker):
    ironic = _pair("primary")
    ironic.nodes["fw-old"] = _ha_node(
        "fw-old", serial="999", mate_serial=SERIAL, parent_node="fw-this"
    )

    with pytest.raises(RuntimeError, match="already has another secondary"):
        _promote(mocker, ironic, "primary")

    assert ironic.updates == []


def test_ha_promotion_refuses_a_primary_that_is_itself_linked(mocker):
    # e.g. a former secondary re-enrolled as the primary.
    ironic = _pair("primary", this={"parent_node": "fw-mate"})

    with pytest.raises(RuntimeError, match="the primary is itself linked to fw-mate"):
        _promote(mocker, ironic, "primary")

    assert ironic.updates == []


@pytest.mark.parametrize("this_role", ["primary", "secondary"])
def test_ha_promotion_relinks_a_secondary_whose_primary_was_deleted(mocker, this_role):
    # The end of a primary replacement: the old primary's node is gone.
    side = "mate" if this_role == "primary" else "this"
    ironic = _pair(this_role, **{side: {"parent_node": "fw-gone"}})
    primary = "fw-this" if this_role == "primary" else "fw-mate"

    _promote(mocker, ironic, this_role)

    assert ironic.updates[0] == (f"fw-{side}", _link_to(primary))
