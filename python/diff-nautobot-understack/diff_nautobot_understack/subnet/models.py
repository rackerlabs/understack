from diffsync import DiffSyncModel


class SubnetModel(DiffSyncModel):
    """Model for comparing OpenStack subnets with Nautobot prefixes."""

    _modelname = "subnet"
    _identifiers = ("id",)
    _attributes = (
        "cidr",
        "network_id",
        "tenant_id",
    )

    id: str
    cidr: str
    network_id: str
    tenant_id: str | None = None
