from uuid import uuid4

import pytest


@pytest.fixture
def sample_uuid():
    return uuid4()
