import ironic.objects


def ironic_ports_for_node(context, node_id: str) -> list:
    return ironic.objects.Port.list_by_node_id(context, node_id)
