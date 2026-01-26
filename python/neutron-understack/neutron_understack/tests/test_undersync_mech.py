"""Tests for the UndersyncMechanismDriver."""

import uuid

import pytest
from neutron_lib.api.definitions import portbindings

from neutron_understack.undersync_mech import UndersyncMechanismDriver
from neutron_understack.undersync_mech import UndersyncPayloadBuilder


@pytest.fixture
def undersync_driver(oslo_config):
    """Create an UndersyncMechanismDriver instance for testing."""
    from neutron_understack.undersync import Undersync

    driver = UndersyncMechanismDriver()
    driver.undersync = Undersync("test_token", "http://test-api")
    driver.dry_run = False
    return driver


@pytest.fixture
def port_with_local_link(port_id):
    """Port dict with local_link_information in binding profile."""
    return {
        "id": str(port_id),
        "network_id": str(uuid.uuid4()),
        "mac_address": "00:11:22:33:44:55",
        portbindings.PROFILE: {
            "local_link_information": [
                {
                    "port_id": "Ethernet1/13",
                    "switch_id": "aa:bb:cc:dd:ee:ff",
                    "switch_info": "leaf-1.example.com",
                }
            ],
            "physical_network": "rack-1",
        },
        portbindings.VNIC_TYPE: portbindings.VNIC_BAREMETAL,
    }


@pytest.fixture
def port_without_local_link(port_id):
    """Port dict without local_link_information."""
    return {
        "id": str(port_id),
        "network_id": str(uuid.uuid4()),
        "mac_address": "00:11:22:33:44:55",
        portbindings.PROFILE: {},
        portbindings.VNIC_TYPE: portbindings.VNIC_NORMAL,
    }


class FakePortContext:
    """Fake port context for testing."""

    def __init__(
        self,
        current: dict,
        original: dict | None = None,
        segment: dict | None = None,
    ):
        self.current = current
        self.original = original or current
        self._segment = segment
        self._plugin_context = FakePluginContext()

    @property
    def bottom_bound_segment(self):
        return self._segment

    @property
    def top_bound_segment(self):
        return self._segment


class FakePortContextNoPlugin:
    """Fake port context without plugin context."""

    def __init__(self, current: dict, segment: dict | None = None):
        self.current = current
        self.original = current
        self._segment = segment

    @property
    def bottom_bound_segment(self):
        return self._segment

    @property
    def top_bound_segment(self):
        return self._segment


class FakePluginContext:
    """Fake plugin context with session."""

    def __init__(self):
        self.session = FakeSession()


class FakeSession:
    """Fake database session."""

    def query(self, model):
        return FakeQuery()


class FakeQuery:
    """Fake SQLAlchemy query."""

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return []

    def first(self):
        return None


class TestUndersyncMechanismDriver:
    """Tests for UndersyncMechanismDriver."""

    def test_should_process_with_local_link(
        self, undersync_driver, port_with_local_link
    ):
        """Port with local_link_information should be processed."""
        context = FakePortContext(port_with_local_link)
        assert undersync_driver._should_process(context) is True

    def test_should_process_without_local_link(
        self, undersync_driver, port_without_local_link
    ):
        """Port without local_link_information should not be processed."""
        context = FakePortContext(port_without_local_link)
        assert undersync_driver._should_process(context) is False

    def test_get_vlan_group_from_binding_profile(
        self, undersync_driver, port_with_local_link
    ):
        """VLAN group should be extracted from binding profile."""
        context = FakePortContext(port_with_local_link)
        vlan_group = undersync_driver._get_vlan_group(context)
        assert vlan_group == "rack-1"

    def test_get_vlan_group_from_segment(
        self, undersync_driver, port_without_local_link
    ):
        """VLAN group should fall back to segment physical_network."""
        segment = {"physical_network": "rack-2", "network_type": "vlan"}
        context = FakePortContext(port_without_local_link, segment=segment)
        vlan_group = undersync_driver._get_vlan_group(context)
        assert vlan_group == "rack-2"

    def test_get_vlan_group_none(self, undersync_driver, port_without_local_link):
        """Should return None if no VLAN group can be determined."""
        context = FakePortContext(port_without_local_link)
        vlan_group = undersync_driver._get_vlan_group(context)
        assert vlan_group is None


class TestCreatePortPostCommit:
    """Tests for create_port_postcommit."""

    def test_triggers_sync_with_local_link(
        self, mocker, undersync_driver, port_with_local_link
    ):
        """Port create with local_link should trigger undersync."""
        mocker.patch.object(undersync_driver.undersync, "sync_with_payload")
        context = FakePortContext(port_with_local_link)

        undersync_driver.create_port_postcommit(context)

        undersync_driver.undersync.sync_with_payload.assert_called_once()

    def test_skips_sync_without_local_link(
        self, mocker, undersync_driver, port_without_local_link
    ):
        """Port create without local_link should not trigger undersync."""
        mocker.patch.object(undersync_driver.undersync, "sync_with_payload")
        context = FakePortContext(port_without_local_link)

        undersync_driver.create_port_postcommit(context)

        undersync_driver.undersync.sync_with_payload.assert_not_called()

    def test_skips_sync_without_plugin_context(
        self, mocker, undersync_driver, port_with_local_link
    ):
        """Port create without plugin context should not trigger undersync."""
        mocker.patch.object(undersync_driver.undersync, "sync_with_payload")
        context = FakePortContextNoPlugin(port_with_local_link)

        undersync_driver.create_port_postcommit(context)

        undersync_driver.undersync.sync_with_payload.assert_not_called()


class TestUpdatePortPostCommit:
    """Tests for update_port_postcommit."""

    def test_triggers_sync_with_local_link(
        self, mocker, undersync_driver, port_with_local_link
    ):
        """Port update with local_link should trigger undersync."""
        mocker.patch.object(undersync_driver.undersync, "sync_with_payload")
        context = FakePortContext(port_with_local_link)

        undersync_driver.update_port_postcommit(context)

        undersync_driver.undersync.sync_with_payload.assert_called_once()

    def test_skips_sync_without_local_link(
        self, mocker, undersync_driver, port_without_local_link
    ):
        """Port update without local_link should not trigger undersync."""
        mocker.patch.object(undersync_driver.undersync, "sync_with_payload")
        context = FakePortContext(port_without_local_link)

        undersync_driver.update_port_postcommit(context)

        undersync_driver.undersync.sync_with_payload.assert_not_called()


class TestDeletePortPostCommit:
    """Tests for delete_port_postcommit."""

    def test_triggers_sync_with_local_link(
        self, mocker, undersync_driver, port_with_local_link
    ):
        """Port delete with local_link should trigger undersync."""
        mocker.patch.object(undersync_driver.undersync, "sync_with_payload")
        context = FakePortContext(port_with_local_link)

        undersync_driver.delete_port_postcommit(context)

        undersync_driver.undersync.sync_with_payload.assert_called_once()

    def test_uses_original_context_for_delete(
        self, mocker, undersync_driver, port_with_local_link, port_without_local_link
    ):
        """Port delete should use original context when current is empty."""
        mocker.patch.object(undersync_driver.undersync, "sync_with_payload")
        # Current port has no local_link, but original did
        context = FakePortContext(
            current=port_without_local_link,
            original=port_with_local_link,
        )

        undersync_driver.delete_port_postcommit(context)

        undersync_driver.undersync.sync_with_payload.assert_called_once()


class TestUndersyncPayloadBuilder:
    """Tests for UndersyncPayloadBuilder."""

    def test_build_payload_structure(self):
        """Payload should have correct structure."""
        context = FakePluginContext()
        builder = UndersyncPayloadBuilder(context, "rack-1")

        payload = builder.build(
            trigger_event="port_create",
            trigger_port_id="test-port-id",
            trigger_network_id="test-network-id",
            dry_run=True,
        )

        assert payload["vlan_group"] == "rack-1"
        assert payload["trigger"]["event"] == "port_create"
        assert payload["trigger"]["port_id"] == "test-port-id"
        assert payload["trigger"]["network_id"] == "test-network-id"
        assert payload["options"]["dry_run"] is True
        assert payload["options"]["force"] is False
        assert "resources" in payload

    def test_build_payload_resources(self):
        """Payload resources should include all required keys."""
        context = FakePluginContext()
        builder = UndersyncPayloadBuilder(context, "rack-1")

        payload = builder.build(trigger_event="port_create")

        resources = payload["resources"]
        assert "networks" in resources
        assert "ports" in resources
        assert "connected_ports" in resources
        assert "segments" in resources
        assert "subnets" in resources
        assert "network_flavors" in resources
        assert "routers" in resources
        assert "address_scopes" in resources
        assert "subnetpools" in resources

    def test_build_payload_with_force(self):
        """Payload should reflect force option."""
        context = FakePluginContext()
        builder = UndersyncPayloadBuilder(context, "rack-1")

        payload = builder.build(trigger_event="port_create", force=True)

        assert payload["options"]["force"] is True


class TestUndersyncClient:
    """Tests for the Undersync client sync_with_payload method."""

    def test_sync_with_payload(self, mocker):
        """sync_with_payload should POST to /v2/sync."""
        from neutron_understack.undersync import Undersync

        undersync = Undersync("test_token", "http://test-api")

        mock_response = mocker.MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = mocker.MagicMock()

        mocker.patch.object(undersync.client, "post", return_value=mock_response)

        payload = {
            "vlan_group": "rack-1",
            "resources": {},
        }

        undersync.sync_with_payload("rack-1", payload)

        undersync.client.post.assert_called_once_with(
            "http://test-api/v2/sync",
            json=payload,
            timeout=90,
        )
