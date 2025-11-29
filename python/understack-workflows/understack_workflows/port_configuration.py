from typing import Annotated

from pydantic import BaseModel
from pydantic import StringConstraints


class PortConfiguration(BaseModel):
    address: Annotated[
        str, StringConstraints(to_lower=True)
    ]  # ironicclient's Port class lowercases this attribute
    node_uuid: str  # using a str here due to ironicclient Port attribute
    name: str  # port name
    pxe_enabled: bool
    local_link_connection: dict
    physical_network: str | None
