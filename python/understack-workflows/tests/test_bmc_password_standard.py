import pytest

from understack_workflows.bmc_password_standard import standard_password


def test_standard_password_good_1():
    plaintext = standard_password("10.3.2.30", "ultra-secret string")
    assert plaintext == "Vbyf7AFhiY2phtD1vcF0"


def test_standard_password_good_2():
    plaintext = standard_password("1.2.3.4", "new secret string")
    assert plaintext == "M5CacBLC/4eVuaTmoH8v"


def test_standard_password_with_empty_input():
    with pytest.raises(ValueError):
        standard_password("", "new secret string")


def test_standard_password_with_bad_input():
    with pytest.raises(ValueError):
        standard_password("elephants", "new secret string")


def test_standard_password_with_empty_key():
    with pytest.raises(ValueError):
        standard_password("1.2.3.4", "")
