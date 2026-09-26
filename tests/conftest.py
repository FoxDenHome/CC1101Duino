import sys
from pathlib import Path

import pytest

# Lets test_protocol import the protocol package standalone, without Home Assistant
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "cc1101duino"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
