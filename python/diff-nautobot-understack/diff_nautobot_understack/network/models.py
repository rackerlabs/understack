from diffsync import DiffSyncModel


class NetworkModel(DiffSyncModel):
    """Model for comparing OpenStack networks with Nautobot UCVNIs.

    Fields match what's actually synced by neutron_network.sync_network_to_nautobot:
    - name: Network name
    - tenant_id: Project/tenant UUID
    - ucvni_id: Provider segmentation ID (VXLAN VNI)
    """

    _modelname = "network"
    _identifiers = ("id",)
    _attributes = (
        "name",
        "tenant_id",
        "ucvni_id",
    )

    id: str
    name: str
    tenant_id: str | None = None
    ucvni_id: int | None = None
