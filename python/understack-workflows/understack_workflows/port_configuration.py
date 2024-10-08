from typing import Annotated

from pydantic import BaseModel
from pydantic import StringConstraints
from pydantic import field_serializer


class PortConfiguration(BaseModel):
    address: Annotated[
        str, StringConstraints(to_lower=True)
    ]  # ironicclient's Port class lowercases this attribute
    uuid: str  # using a str here to due to ironicclient Port attribute
    node_uuid: str  # using a str here due to ironicclient Port attribute
    name: str  # port name

    # Ironic requires the port names to be globally unique
    @field_serializer("name")
    def serialize_name(self, name: str):
        return f"{self.uuid} {name}"
