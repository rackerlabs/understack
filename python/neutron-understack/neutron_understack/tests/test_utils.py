from unittest.mock import Mock

import pytest
from neutron.plugins.ml2.driver_context import portbindings

from neutron_understack import utils


class TestFetchConnectedInterfaceUUID:
    def test_with_normal_uuid(self, port_context, port_id):
        result = utils.fetch_connected_interface_uuid(
            binding_profile=port_context.current["binding:profile"], nautobot=Mock()
        )
        assert result == str(port_id)

    @pytest.mark.parametrize("binding_profile", [{"port_id": 11}], indirect=True)
    def test_with_integer(self, port_context):
        fake_nautobot = Mock()
        fake_nautobot.get_interface_uuid.return_value = "FAKE ID"

        result = utils.fetch_connected_interface_uuid(
            binding_profile=port_context.current["binding:profile"],
            nautobot=fake_nautobot,
        )
        assert result == "FAKE ID"

        fake_nautobot.get_interface_uuid.assert_called_once_with(
            device_name="a1-1-1.iad3.rackspace.net",
            interface_name=11,
        )


class TestParentPortIsBound:
    def test_truthy_conditions(self, port_object):
        """Truthy conditions.

        When vif type is "other", vnic_type is "baremetal"
        and binding profile is present.
        """
        result = utils.parent_port_is_bound(port_object)
        assert result is True

    def test_vif_type_unbound(self, port_object):
        port_object.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
        result = utils.parent_port_is_bound(port_object)
        assert result is False

    def test_vnic_type_normal(self, port_object):
        port_object.bindings[0].vnic_type = portbindings.VNIC_NORMAL
        result = utils.parent_port_is_bound(port_object)
        assert result is False

    def test_no_binding_profile(self, port_object):
        port_object.bindings[0].profile = {}
        result = utils.parent_port_is_bound(port_object)
        assert result is False
