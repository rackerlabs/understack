"""Store firmware versions a driver read from a device as firmware components."""

from ironic import objects


def sync(task, settings: list[dict]) -> None:
    """Create or update the node's firmware components to match ``settings``.

    Each setting is a dict with ``component``, ``current_version``, ``vendor``,
    ``model`` and ``serial_number``. A component whose version changed has the
    new version recorded as ``last_version_flashed`` too.
    """
    node_id = task.node.id
    create_list, update_list, _ = (
        objects.FirmwareComponentList.sync_firmware_components(
            task.context, node_id, settings
        )
    )
    for new in create_list:
        objects.FirmwareComponent(
            task.context,
            node_id=node_id,
            component=new["component"],
            current_version=new["current_version"],
            vendor=new["vendor"],
            model=new["model"],
            serial_number=new["serial_number"],
        ).create()
    for up in update_list:
        existing = objects.FirmwareComponent.get(
            task.context, node_id=node_id, name=up["component"]
        )
        if existing.current_version != up["current_version"]:
            existing.last_version_flashed = up["current_version"]
            existing.current_version = up["current_version"]
        existing.vendor = up["vendor"]
        existing.model = up["model"]
        existing.serial_number = up["serial_number"]
        existing.save()
