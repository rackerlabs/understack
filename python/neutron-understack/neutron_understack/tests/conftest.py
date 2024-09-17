import random
import uuid

import pytest


@pytest.fixture
def device_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mac_address() -> str:
    return (
        f"{random.randint(0, 255):02x}:"
        f"{random.randint(0, 255):02x}:"
        f"{random.randint(0, 255):02x}:"
        f"{random.randint(0, 255):02x}:"
        f"{random.randint(0, 255):02x}:"
        f"{random.randint(0, 255):02x}"
    )


@pytest.fixture
def network_id() -> uuid.UUID:
    return uuid.uuid4()
