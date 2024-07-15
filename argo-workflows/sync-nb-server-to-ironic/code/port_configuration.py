from pydantic import BaseModel, StringConstraints
from typing import Annotated


class PortConfiguration(BaseModel):
    address: Annotated[str, StringConstraints(to_lower=True)]  # ironicclient's Port class lowercases this attribute
    uuid: str  # using a str here to remain consistent with the ironicclient Port attribute
    node_uuid: str  # using a str here to remain consistent with the ironicclient Port attribute
