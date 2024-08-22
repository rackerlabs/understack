import uuid

import pytest


@pytest.fixture
def device_id() -> uuid.UUID:
    return uuid.uuid4()
