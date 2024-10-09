import pytest
from understack_workflows.bmc_password_standard import standard_password

def test_standard_password():
    assert standard_password("10.3.2.30", "ultra-secret string") == 'DdushPf7IUTs6oya3ADS0OM3'
    assert standard_password("1.2.3.4", "new secret string") == 'guW1SYE7HmrOrNXF75qmiscd'
