from neutron.objects import ports as port_obj
from neutron.plugins.ml2.driver_context import PortContext
from neutron.plugins.ml2.driver_context import portbindings
from neutron_lib import context as n_context


def fetch_subport_network_id(subport_id):
    context = n_context.get_admin_context()
    neutron_port = port_obj.Port.get_object(context, id=subport_id)
    return neutron_port.network_id


def baremetal_vif_type_other_not_changed(context: PortContext) -> bool:
    return bool(
        context.current["binding:vnic_type"] == "baremetal"
        and context.vif_type == portbindings.VIF_TYPE_OTHER
        and context.original_vif_type == portbindings.VIF_TYPE_OTHER
    )


def baremetal_vif_type_other_changed_to_unbound(context: PortContext) -> bool:
    return bool(
        context.current["binding:vnic_type"] == "baremetal"
        and context.vif_type == portbindings.VIF_TYPE_UNBOUND
        and context.original_vif_type == portbindings.VIF_TYPE_OTHER
    )


def subports_with_port_id_only(trunk_details: dict) -> list:
    return [
        {"port_id": subport.get("port_id")}
        for subport in trunk_details.get("sub_ports", [])
    ]


def diffed_subports(current_subports: list, original_subports: list) -> dict:
    subports_added = [
        subport for subport in current_subports if subport not in original_subports
    ]
    subports_removed = [
        subport for subport in original_subports if subport not in current_subports
    ]
    return {"subports_added": subports_added, "subports_removed": subports_removed}


def changed_subports(context: PortContext) -> dict | None:
    current_trunk_details = context.current.get("trunk_details", {})
    original_trunk_details = context.original.get("trunk_details", {})
    if current_trunk_details == original_trunk_details:
        return

    current_subports = subports_with_port_id_only(current_trunk_details)
    original_subports = subports_with_port_id_only(original_trunk_details)

    return diffed_subports(current_subports, original_subports)
