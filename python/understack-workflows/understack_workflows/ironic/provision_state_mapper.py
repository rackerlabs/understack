class ProvisioningStatusMapper:
    STATUS_MAP = {
        "active": "Active",
        "enroll": "Planned",
        "available": "Inventory",
        "deploy failed": "Quarantine",
        "error": "Quarantine",
        "rescue": "Quarantine",
        "rescue failed": "Quarantine",
        "unrescueing": "Quarantine",
        "manageable": "Quarantine",
        "inspecting": "Provisioning",
        "deploying": "Provisioning",
        "cleaning": "Quarantine",
        "deleting": "Decom",
    }
    ALL_IRONIC_STATES = [
        "enroll",
        "verifying",
        "manageable",
        "inspecting",
        "inspect wait",
        "inspect failed",
        "cleaning",
        "clean wait",
        "available",
        "deploying",
        "wait call-back",
        "deploy failed",
        "active",
        "deleting",
        "error",
        "adopting",
        "rescuing",
        "rescue wait",
        "rescue failed",
        "rescue",
        "unrescuing",
        "unrescue failed",
        "servicing",
        "service wait",
        "service failed",
    ]

    @classmethod
    def translate_to_nautobot(cls, provisioning_state: str) -> str | None:
        """Translate ironic provisioning status to Nautobot Status.

        This method intends to return Nautobot Status only during some of the
        transitions. For the provision_states that are valid in Ironic's world,
        but don't result in a new state in Nautobot, special value of None will
        be returned.
        :param: provisioning_state
        :type arg: str
        :raises: :class:`ValueError`: invalid provisioning_state provided
        :returns: Name of a Nautobot Status or None
        :rtype: str
        """
        if provisioning_state in cls.STATUS_MAP:
            return cls.STATUS_MAP[provisioning_state]
        elif provisioning_state in cls.ALL_IRONIC_STATES:
            return None

        raise ValueError(f"Unknown {provisioning_state=}")
