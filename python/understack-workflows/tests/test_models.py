from understack_workflows.models import NIC


def test_nic():
    value = "test"
    a = NIC(name=value, location=value, interfaces=[], model=value)

    assert a.name == value
    assert a.location == value
    assert a.model == value
