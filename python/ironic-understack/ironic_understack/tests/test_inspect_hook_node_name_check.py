import pytest
from ironic.common import exception
from oslo_utils import uuidutils

from ironic_understack.inspect_hook_node_name_check import InspectHookNodeNameCheck
from ironic_understack.inspect_hook_node_name_check import _manufacturer_slug


def _make_task(mocker, node_name):
    node = mocker.Mock(id=1234, uuid=uuidutils.generate_uuid())
    node.name = node_name
    return mocker.Mock(node=node)


class TestInspectHookNodeNameCheck:
    def test_matching_name_passes(self, mocker):
        task = _make_task(mocker, "Dell Inc._SN123")
        inventory = {
            "system_vendor": {
                "serial_number": "SN123",
                "manufacturer": "Dell Inc.",
            }
        }

        # Should not raise
        InspectHookNodeNameCheck()(task, inventory, {})

    def test_mismatched_name_raises(self, mocker):
        task = _make_task(mocker, "Wrong-Name")
        inventory = {
            "system_vendor": {
                "serial_number": "SN123",
                "manufacturer": "Dell Inc.",
            }
        }

        with pytest.raises(RuntimeError, match="Hardware Identity Crisis"):
            InspectHookNodeNameCheck()(task, inventory, {})

    def test_missing_serial_number_raises(self, mocker):
        task = _make_task(mocker, "Dell-SN123")
        inventory = {
            "system_vendor": {
                "manufacturer": "Dell Inc.",
            }
        }

        with pytest.raises(exception.InvalidNodeInventory, match="No serial number"):
            InspectHookNodeNameCheck()(task, inventory, {})

    def test_missing_manufacturer_raises(self, mocker):
        task = _make_task(mocker, "Dell-SN123")
        inventory = {
            "system_vendor": {
                "serial_number": "SN123",
            }
        }

        with pytest.raises(exception.InvalidNodeInventory, match="No manufacturer"):
            InspectHookNodeNameCheck()(task, inventory, {})

    def test_sku_field_is_not_used_for_serial(self, mocker):
        """serial_number comes only from serial_number, not sku."""
        task = _make_task(mocker, "Dell-SKU999")
        inventory = {
            "system_vendor": {
                "sku": "SKU999",
                "manufacturer": "Dell Inc.",
            }
        }

        with pytest.raises(exception.InvalidNodeInventory, match="No serial number"):
            InspectHookNodeNameCheck()(task, inventory, {})

    def test_empty_system_vendor(self, mocker):
        task = _make_task(mocker, "Dell-SN123")
        inventory = {"system_vendor": {}}

        with pytest.raises(exception.InvalidNodeInventory, match="No serial number"):
            InspectHookNodeNameCheck()(task, inventory, {})


class TestManufacturerSlug:
    def test_dell(self):
        assert _manufacturer_slug("Dell Inc.") == "Dell"

    def test_dell_uppercase(self):
        assert _manufacturer_slug("DELL") == "Dell"

    def test_hp(self):
        assert _manufacturer_slug("HPE") == "HP"

    def test_hp_lowercase(self):
        assert _manufacturer_slug("hp") == "HP"

    def test_other_replaces_spaces(self):
        assert _manufacturer_slug("Super Micro") == "Super_Micro"
