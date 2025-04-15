import pytest
from neutron.plugins.ml2.driver_context import portbindings

from neutron_understack import utils


class TestFetchConnectedInterfaceUUID:
    def test_with_normal_uuid(self, port_context, port_id):
        result = utils.fetch_connected_interface_uuid(
            port_context.current["binding:profile"]
        )
        assert result == str(port_id)

    @pytest.mark.parametrize("binding_profile", [{"port_id": 11}], indirect=True)
    def test_with_integer(self, port_context):
        with pytest.raises(ValueError):
            utils.fetch_connected_interface_uuid(
                port_context.current["binding:profile"]
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


class TestVlanGroupNameFromBindingProfile:
    def test_when_switch_name_is_present(self, port_object):
        binding_profile = port_object.bindings[0].profile
        result = utils.vlan_group_name_from_binding_profile(binding_profile)
        assert result == "a1-1-network"

    def test_when_switch_name_is_not_present(self, port_object):
        binding_profile = port_object.bindings[0].profile
        binding_profile["local_link_information"][0].pop("switch_info")
        result = utils.vlan_group_name_from_binding_profile(binding_profile)
        assert result is None

    def test_when_switch_name_is_non_standard(self, port_object):
        binding_profile = port_object.bindings[0].profile
        binding_profile["local_link_information"][0]["switch_info"] = "blah"
        with pytest.raises(ValueError):
            utils.vlan_group_name_from_binding_profile(binding_profile)
