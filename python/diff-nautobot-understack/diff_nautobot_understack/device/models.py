from diffsync import DiffSyncModel


class DeviceModel(DiffSyncModel):
    """Model for comparing Ironic nodes with Nautobot devices."""

    _modelname = "device"
    _identifiers = ("id",)
    _attributes = (
        "name",
        "status",
        "tenant_id",
    )

    id: str
    name: str | None = None
    status: str | None = None
    tenant_id: str | None = None
