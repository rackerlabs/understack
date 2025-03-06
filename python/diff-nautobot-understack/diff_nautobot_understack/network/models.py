from diffsync import DiffSyncModel


class NetworkModel(DiffSyncModel):
    _modelname = "network"
    _identifiers = ("id",)
    _attributes = (
        "name",
        "status",
        "provider_physical_network",
        "vni_id",
    )

    id: str
    name: str
    status: str
    provider_physical_network: str | None = None
    vni_id: int | None = None
