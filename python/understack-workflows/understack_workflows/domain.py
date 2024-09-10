"""helper for OpenStack Domain IDs."""

import uuid


class DefaultDomain:
    @property
    def hex(self):
        return "default"


def domain_id(data):
    return DefaultDomain() if data == "default" else uuid.UUID(data)
