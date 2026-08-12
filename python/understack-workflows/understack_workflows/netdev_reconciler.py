import json
import logging
from dataclasses import dataclass

from ironicclient.common.apiclient import exceptions as ironic_exceptions
from ironicclient.common.utils import args_array_to_patch
from ironicclient.v1.node import Node

from understack_workflows import ironic_node
from understack_workflows.ironic.client import IronicClient

logger = logging.getLogger(__name__)

DEFAULT_RESOURCE_CLASS = "generic"
PLACEHOLDER_SWITCH_ID = "00:00:00:00:00:00"

# Provision states from which enrollment can proceed to "available".
# Anything else (e.g. "active", "deploying") means the node is in use
# and we are not touching it.
REENROLLABLE_STATES = {"enroll", "manageable", "available"}

# Keys for each entry in the --ports list. The label is the stable identity
# for a port on a node; the MAC and connection metadata are editable values
# that converge on re-runs. switch_id is optional: when omitted the placeholder
# is used (and an existing real value is preserved).
REQUIRED_PORT_FIELDS = ("label", "mac", "switch", "intf")
OPTIONAL_PORT_FIELDS = ("switch_id",)
ALLOWED_PORT_FIELDS = frozenset(REQUIRED_PORT_FIELDS + OPTIONAL_PORT_FIELDS)


@dataclass(frozen=True)
class NetdevPort:
    label: str
    mac: str
    switch: str
    interface: str
    switch_id: str | None = None


def _has_cmdb_id(external_cmdb_id: int | str | None) -> bool:
    """Return True unless the CMDB ID is unset (None or empty string).

    A truthiness check would wrongly drop a valid CMDB ID of 0.
    """
    return external_cmdb_id not in (None, "")


def parse_ports_arg(raw: str) -> list[dict]:
    """Parse the --ports argument (a JSON array) into a list of dicts."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--ports must be valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("--ports must be a JSON array of port objects")
    return data


def build_netdev_ports(ports: list[dict]) -> list[NetdevPort]:
    """Validate the ports list and return NetdevPort objects.

    Labels are stable caller-provided identities (e.g. port1, port2, ...).
    MAC addresses and labels must be unique within the request.
    """
    if not ports:
        raise ValueError("At least one port must be provided")

    result: list[NetdevPort] = []
    seen_labels: set[str] = set()
    seen_macs: set[str] = set()
    for index, entry in enumerate(ports, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Port {index} must be a JSON object")
        missing = [key for key in REQUIRED_PORT_FIELDS if not entry.get(key)]
        if missing:
            raise ValueError(
                f"Port {index} is missing required field(s): {', '.join(missing)}"
            )
        # Required fields must be strings, not just truthy: a non-string like
        # {"mac": 123} would otherwise reach .lower() and raise an opaque
        # AttributeError. switch_id is optional but, when present, must be a str.
        non_string = [
            key for key in REQUIRED_PORT_FIELDS if not isinstance(entry[key], str)
        ]
        if non_string:
            raise ValueError(
                f"Port {index} field(s) must be strings: {', '.join(non_string)}"
            )
        switch_id = entry.get("switch_id")
        if switch_id is not None and not isinstance(switch_id, str):
            raise ValueError(
                f"Port {index} switch_id must be a string, got {switch_id!r}"
            )
        unknown = set(entry) - ALLOWED_PORT_FIELDS
        if unknown:
            raise ValueError(
                f"Port {index} has unknown field(s): {', '.join(sorted(unknown))}"
            )
        # Labels are case-sensitive identities: they map directly to the Ironic
        # port name (node_name:label), and that lookup is case-sensitive, so
        # dedup must be too.
        if entry["label"] in seen_labels:
            raise ValueError(f"Duplicate label {entry['label']} in ports list")
        seen_labels.add(entry["label"])
        mac_key = entry["mac"].lower()
        if mac_key in seen_macs:
            raise ValueError(f"Duplicate MAC {entry['mac']} in ports list")
        seen_macs.add(mac_key)
        result.append(
            NetdevPort(
                label=entry["label"],
                mac=entry["mac"],
                switch=entry["switch"],
                interface=entry["intf"],
                switch_id=entry.get("switch_id"),
            )
        )
    return result


def enroll(
    *,
    name: str,
    physical_network: str,
    ports: list[dict],
    external_cmdb_id: int | str | None = None,
    resource_class: str | None = DEFAULT_RESOURCE_CLASS,
    driver_info: dict | None = None,
    extra: dict | None = None,
) -> None:
    effective_resource_class = resource_class or DEFAULT_RESOURCE_CLASS
    netdev_ports = build_netdev_ports(ports)

    # driver_info/extra are generic Ironic node metadata a caller may want set
    # (e.g. the firewall workflow records management access in driver_info).
    # They are written inside the enrollment lifecycle -- at node create, or
    # patched before the node is made available -- so the node is never
    # allocatable in an under-described state. external_cmdb_id is folded into
    # extra for convenience.
    node_driver_info = dict(driver_info or {})
    node_extra = dict(extra or {})
    if _has_cmdb_id(external_cmdb_id):
        node_extra["external_cmdb_id"] = external_cmdb_id

    logger.info(
        "Starting enroll-netdev workflow name=%s physical_network=%s "
        "resource_class=%s port_count=%s",
        name,
        physical_network,
        effective_resource_class,
        len(netdev_ports),
    )
    if node_driver_info:
        logger.info("Recording driver_info=%s on the Ironic node", node_driver_info)
    if node_extra:
        logger.info("Recording extra=%s on the Ironic node", node_extra)

    client = IronicClient()
    node, created = find_or_create_netdev_node(
        client=client,
        name=name,
        resource_class=effective_resource_class,
        driver_info=node_driver_info,
        extra=node_extra,
    )

    node_ports = list(client.list_ports(node.uuid))
    ports_by_mac = {(p.address or "").lower(): p for p in node_ports}
    ports_by_name = {p.name: p for p in node_ports if p.name}

    # Plan first (no mutations): decide which ports need create/update. This
    # lets us skip all work when a re-run has nothing to change, only step the
    # node's provision state when we actually have port work to do, and fail on
    # a port conflict before mutating anything.
    plans = [
        plan_netdev_port(
            node=node,
            node_name=name,
            physical_network=physical_network,
            port=port,
            existing=ports_by_name.get(f"{name}:{port.label}"),
            ports_by_mac=ports_by_mac,
        )
        for port in netdev_ports
    ]
    pending = [plan for plan in plans if plan is not None]

    warn_orphan_ports(node, name, node_ports, netdev_ports)

    state = node.provision_state

    # Step an available node out of the allocatable pool BEFORE mutating it, so
    # it never sits available with stale ports (or a changed resource_class)
    # while its ports are still being reconciled. Ironic also refuses port
    # connectivity changes while a node is available, so this is required for
    # port work. A metadata-only change on an available node (no pending ports)
    # is patched in place below and stays available -- its ports are already
    # correct, so re-pooling is safe.
    if pending and state == "available":
        logger.info(
            "[node:%s] Stepping available -> manageable to apply changes",
            node.uuid,
        )
        ironic_node.transition(node, target_state="manage", expected_state="manageable")
        state = "manageable"

    # Apply the reused node's metadata after planning has validated (so a port
    # conflict does not leave metadata half-updated) and after any step-down
    # above (so a resource_class change is applied while out of the pool). A
    # freshly created node already has these set from create.
    metadata_changed = False
    if not created:
        metadata_changed = update_node_metadata(
            client=client,
            node=node,
            resource_class=effective_resource_class,
            driver_info=node_driver_info,
            extra=node_extra,
        )

    if not pending and state == "available":
        if metadata_changed:
            logger.info(
                "[node:%s] Node metadata updated; already available with no "
                "port changes",
                node.uuid,
            )
        else:
            logger.info(
                "[node:%s] Node already available and up to date, nothing to do",
                node.uuid,
            )
        return

    for plan in pending:
        apply_port_plan(
            client=client,
            node=node,
            node_name=name,
            physical_network=physical_network,
            plan=plan,
        )

    make_available(node, state)
    logger.info(
        "Completed enroll-netdev workflow name=%s node_uuid=%s",
        name,
        node.uuid,
    )


def warn_orphan_ports(
    node: Node, node_name: str, node_ports: list, netdev_ports: list[NetdevPort]
) -> None:
    """Warn about existing ports on the node that are not in the request.

    These are left in place rather than deleted: removing ports on a re-run
    would let a shortened request silently destroy data.
    """
    requested = {f"{node_name}:{port.label}" for port in netdev_ports}
    for existing in node_ports:
        if existing.name not in requested:
            logger.warning(
                "[node:%s] Existing port uuid=%s name=%s mac=%s is not in the "
                "request by label; leaving it in place",
                node.uuid,
                existing.uuid,
                existing.name,
                existing.address,
            )


def find_or_create_netdev_node(
    *,
    client: IronicClient,
    name: str,
    resource_class: str,
    driver_info: dict,
    extra: dict,
) -> tuple[Node, bool]:
    """Find an existing netdev node by name, or create one.

    Returns (node, created). A reused node is validated (driver and provision
    state) but not mutated here; its metadata is applied later by the caller
    once port planning has succeeded.
    """
    try:
        node = client.get_node(name)
    except ironic_exceptions.NotFound:
        node = create_netdev_node(
            client=client,
            name=name,
            resource_class=resource_class,
            driver_info=driver_info,
            extra=extra,
        )
        return node, True

    if node.driver != "netdev":
        raise RuntimeError(
            f"Node {name} ({node.uuid}) already exists with driver "
            f"{node.driver!r}; refusing to enroll it as a netdev"
        )

    if node.provision_state not in REENROLLABLE_STATES:
        raise RuntimeError(
            f"[node:{node.uuid}] Cannot enroll node in provision_state "
            f"{node.provision_state!r}; expected one of "
            f"{sorted(REENROLLABLE_STATES)}"
        )

    logger.info(
        "[node:%s] Reusing existing netdev node name=%s provision_state=%s",
        node.uuid,
        name,
        node.provision_state,
    )
    return node, False


def update_node_metadata(
    *,
    client: IronicClient,
    node: Node,
    resource_class: str,
    driver_info: dict,
    extra: dict,
) -> bool:
    """Patch resource_class/driver_info/extra keys that differ from the node.

    Only the supplied driver_info/extra keys are considered; existing keys the
    request does not mention are left untouched. Returns True if a patch was
    sent, so the caller can report accurately.
    """
    updates = []
    if getattr(node, "resource_class", None) != resource_class:
        updates.append(f"resource_class={resource_class}")

    node_driver_info = getattr(node, "driver_info", None) or {}
    for key, value in driver_info.items():
        if node_driver_info.get(key) != value:
            updates.append(f"driver_info/{key}={value}")

    node_extra = getattr(node, "extra", None) or {}
    for key, value in extra.items():
        if node_extra.get(key) != value:
            updates.append(f"extra/{key}={value}")

    if not updates:
        return False

    logger.info("[node:%s] Updating node metadata %s", node.uuid, updates)
    client.update_node(node.uuid, args_array_to_patch("add", updates))
    return True


def create_netdev_node(
    *,
    client: IronicClient,
    name: str,
    resource_class: str,
    driver_info: dict,
    extra: dict,
) -> Node:
    node_data = {
        "automated_clean": False,
        "driver": "netdev",
        "name": name,
        "resource_class": resource_class,
    }
    if driver_info:
        node_data["driver_info"] = driver_info
    if extra:
        node_data["extra"] = extra

    logger.info(
        "Creating netdev Ironic node name=%s driver=%s "
        "resource_class=%s automated_clean=%s",
        node_data["name"],
        node_data["driver"],
        node_data["resource_class"],
        node_data["automated_clean"],
    )
    node = client.create_node(node_data)
    logger.info("Created netdev Ironic node name=%s uuid=%s", name, node.uuid)
    return node


def plan_netdev_port(
    *,
    node: Node,
    node_name: str,
    physical_network: str,
    port: NetdevPort,
    existing=None,
    ports_by_mac: dict | None = None,
) -> dict | None:
    """Decide what a single port needs, without mutating anything.

    Returns a plan dict describing the action, or None if the port already
    matches the request. Raises on a MAC conflict that would imply an
    automatic label move/rename.

    Plan shapes:
      {"kind": "create", "port": NetdevPort}
      {"kind": "update", "existing": Port, "patch": [json-patch ops]}
    """
    port_name = f"{node_name}:{port.label}"
    ports_by_mac = ports_by_mac or {}
    mac_owner = ports_by_mac.get(port.mac.lower())

    if existing is None:
        if mac_owner is not None:
            raise RuntimeError(
                f"[node:{node.uuid}] Cannot create port {port_name} with MAC "
                f"{port.mac}: that MAC is already used by port {mac_owner.uuid} "
                f"name={mac_owner.name}. Delete or rename that existing port "
                "manually if this is an intentional label change."
            )
        return {"kind": "create", "port": port}

    current_llc = existing.local_link_connection or {}

    # switch_id rule: an explicit value in the request wins (lets operators set
    # or correct it). Otherwise preserve a real value already recorded, and only
    # (re)write the placeholder while the stored value is still placeholder/unset.
    # switch_info and port_id always converge to the request.
    current_switch_id = current_llc.get("switch_id")
    if port.switch_id not in (None, ""):
        switch_id = port.switch_id
    elif current_switch_id in (None, "", PLACEHOLDER_SWITCH_ID):
        switch_id = PLACEHOLDER_SWITCH_ID
    else:
        switch_id = current_switch_id

    desired_llc = {
        "switch_id": switch_id,
        "switch_info": port.switch,
        "port_id": port.interface,
    }

    patch = []
    if (existing.address or "").lower() != port.mac.lower():
        if mac_owner is not None and mac_owner.uuid != existing.uuid:
            raise RuntimeError(
                f"[node:{node.uuid}] Cannot update port {port_name} to MAC "
                f"{port.mac}: that MAC is already used by port {mac_owner.uuid} "
                f"name={mac_owner.name}. Delete or rename that existing port "
                "manually if this is an intentional label change."
            )
        patch.append({"op": "add", "path": "/address", "value": port.mac})
    if existing.physical_network != physical_network:
        patch.append(
            {"op": "add", "path": "/physical_network", "value": physical_network}
        )
    if getattr(existing, "category", None) != "network":
        patch.append({"op": "add", "path": "/category", "value": "network"})
    if any(current_llc.get(key) != value for key, value in desired_llc.items()):
        # Replace the whole object rather than nested keys: Ironic allows
        # local_link_connection to be null, and a nested JSON patch would fail
        # when the parent object is absent.
        patch.append(
            {"op": "add", "path": "/local_link_connection", "value": desired_llc}
        )

    if not patch:
        logger.info(
            "[node:%s] Port name=%s mac=%s already up to date, skipping",
            node.uuid,
            port_name,
            port.mac,
        )
        return None

    return {"kind": "update", "existing": existing, "patch": patch}


def apply_port_plan(
    *,
    client: IronicClient,
    node: Node,
    node_name: str,
    physical_network: str,
    plan: dict,
) -> None:
    """Apply one plan produced by plan_netdev_port.

    The node must already be in a state that permits port connectivity changes
    (enroll or manageable); the caller is responsible for that.
    """
    if plan["kind"] == "create":
        create_netdev_port(
            client=client,
            node=node,
            node_name=node_name,
            physical_network=physical_network,
            port=plan["port"],
        )
        return

    existing = plan["existing"]
    patch = plan["patch"]
    logger.info(
        "[node:%s] Updating existing port uuid=%s mac=%s patch=%s",
        node.uuid,
        existing.uuid,
        existing.address,
        patch,
    )
    client.update_port(existing.uuid, patch)


def create_netdev_port(
    *,
    client: IronicClient,
    node: Node,
    node_name: str,
    physical_network: str,
    port: NetdevPort,
) -> None:
    port_name = f"{node_name}:{port.label}"
    switch_id = port.switch_id or PLACEHOLDER_SWITCH_ID
    port_data = {
        "address": port.mac,
        "category": "network",
        "local_link_connection": {
            "switch_id": switch_id,
            "switch_info": port.switch,
            "port_id": port.interface,
        },
        "name": port_name,
        "node_uuid": node.uuid,
        "physical_network": physical_network,
    }

    logger.info(
        "[node:%s] Creating baremetal port name=%s mac=%s "
        "physical_network=%s switch_id=%s switch_info=%s port_id=%s "
        "category=network",
        node.uuid,
        port_name,
        port.mac,
        physical_network,
        switch_id,
        port.switch,
        port.interface,
    )
    created_port = client.create_port(port_data)
    logger.info(
        "[node:%s] Created baremetal port name=%s uuid=%s",
        node.uuid,
        port_name,
        getattr(created_port, "uuid", ""),
    )


def make_available(node: Node, state: str) -> None:
    """Drive the node to "available" given its current provision state.

    ``state`` is passed in rather than read from the node because earlier steps
    may have already transitioned it (e.g. available to manageable) without
    refreshing the local node object.
    """
    if state == "available":
        logger.info("[node:%s] Node is already available", node.uuid)
        return

    if state not in REENROLLABLE_STATES:
        raise RuntimeError(
            f"[node:{node.uuid}] Cannot make node available from "
            f"provision_state {state!r}"
        )

    if state == "enroll":
        logger.info(
            "[node:%s] Requesting manage transition, expecting manageable",
            node.uuid,
        )
        ironic_node.transition(node, target_state="manage", expected_state="manageable")
        logger.info("[node:%s] Node is manageable", node.uuid)

    logger.info(
        "[node:%s] Requesting provide transition, expecting available",
        node.uuid,
    )
    ironic_node.transition(node, target_state="provide", expected_state="available")
    logger.info("[node:%s] Node is available", node.uuid)
