"""Tests for resync_ironic_to_nautobot module."""

from unittest.mock import MagicMock
from unittest.mock import patch

from understack_workflows.main.resync_ironic_to_nautobot import SyncResult
from understack_workflows.main.resync_ironic_to_nautobot import argument_parser
from understack_workflows.main.resync_ironic_to_nautobot import main
from understack_workflows.main.resync_ironic_to_nautobot import sync_nodes


class TestSyncResult:
    """Test cases for SyncResult dataclass."""

    def test_defaults(self):
        result = SyncResult()
        assert result.total == 0
        assert result.failed == 0
        assert result.succeeded == 0

    def test_succeeded_calculation(self):
        result = SyncResult(total=10, failed=3)
        assert result.succeeded == 7

    def test_all_failed(self):
        result = SyncResult(total=5, failed=5)
        assert result.succeeded == 0

    def test_none_failed(self):
        result = SyncResult(total=5, failed=0)
        assert result.succeeded == 5


class TestArgumentParser:
    """Test cases for argument_parser function."""

    def test_default_args(self):
        parser = argument_parser()
        args = parser.parse_args([])
        assert args.node is None
        assert args.dry_run is False

    def test_node_arg(self):
        parser = argument_parser()
        args = parser.parse_args(["--node", "test-uuid"])
        assert args.node == "test-uuid"

    def test_dry_run_arg(self):
        parser = argument_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True


class TestSyncNodes:
    """Test cases for sync_nodes function."""

    @patch("understack_workflows.main.resync_ironic_to_nautobot.IronicClient")
    @patch(
        "understack_workflows.main.resync_ironic_to_nautobot.sync_device_to_nautobot"
    )
    def test_sync_all_nodes_success(self, mock_sync, mock_ironic_class):
        mock_ironic = MagicMock()
        mock_ironic_class.return_value = mock_ironic
        mock_node1 = MagicMock(uuid="uuid-1", name="node-1")
        mock_node2 = MagicMock(uuid="uuid-2", name="node-2")
        mock_ironic.list_nodes.return_value = [mock_node1, mock_node2]
        mock_sync.return_value = 0

        nautobot = MagicMock()
        result = sync_nodes(nautobot)

        assert result.total == 2
        assert result.failed == 0
        assert mock_sync.call_count == 2

    @patch("understack_workflows.main.resync_ironic_to_nautobot.IronicClient")
    @patch(
        "understack_workflows.main.resync_ironic_to_nautobot.sync_device_to_nautobot"
    )
    def test_sync_single_node(self, mock_sync, mock_ironic_class):
        mock_ironic = MagicMock()
        mock_ironic_class.return_value = mock_ironic
        mock_node = MagicMock(uuid="uuid-1", name="node-1")
        mock_ironic.get_node.return_value = mock_node
        mock_sync.return_value = 0

        nautobot = MagicMock()
        result = sync_nodes(nautobot, node_uuid="uuid-1")

        assert result.total == 1
        assert result.failed == 0
        mock_ironic.get_node.assert_called_once_with("uuid-1")

    @patch("understack_workflows.main.resync_ironic_to_nautobot.IronicClient")
    @patch(
        "understack_workflows.main.resync_ironic_to_nautobot.sync_device_to_nautobot"
    )
    def test_sync_with_failures(self, mock_sync, mock_ironic_class):
        mock_ironic = MagicMock()
        mock_ironic_class.return_value = mock_ironic
        mock_node1 = MagicMock(uuid="uuid-1", name="node-1")
        mock_node2 = MagicMock(uuid="uuid-2", name="node-2")
        mock_ironic.list_nodes.return_value = [mock_node1, mock_node2]
        mock_sync.side_effect = [0, 1]  # First succeeds, second fails

        nautobot = MagicMock()
        result = sync_nodes(nautobot)

        assert result.total == 2
        assert result.failed == 1
        assert result.succeeded == 1

    @patch("understack_workflows.main.resync_ironic_to_nautobot.IronicClient")
    def test_dry_run_skips_sync(self, mock_ironic_class):
        mock_ironic = MagicMock()
        mock_ironic_class.return_value = mock_ironic
        mock_node = MagicMock(uuid="uuid-1", name="node-1")
        mock_ironic.list_nodes.return_value = [mock_node]

        nautobot = MagicMock()
        result = sync_nodes(nautobot, dry_run=True)

        assert result.total == 1
        assert result.failed == 0


class TestMain:
    """Test cases for main function."""

    @patch("understack_workflows.main.resync_ironic_to_nautobot.sync_nodes")
    @patch("understack_workflows.main.resync_ironic_to_nautobot.pynautobot")
    @patch("understack_workflows.main.resync_ironic_to_nautobot.credential")
    @patch("understack_workflows.main.resync_ironic_to_nautobot.setup_logger")
    @patch("understack_workflows.main.resync_ironic_to_nautobot.argument_parser")
    def test_main_success(
        self, mock_parser, mock_logger, mock_cred, mock_pynb, mock_sync
    ):
        mock_args = MagicMock()
        mock_args.nautobot_token = "token"
        mock_args.nautobot_url = "http://nautobot"
        mock_args.node = None
        mock_args.dry_run = False
        mock_parser.return_value.parse_args.return_value = mock_args
        mock_sync.return_value = SyncResult(total=5, failed=0)

        result = main()

        assert result == 0

    @patch("understack_workflows.main.resync_ironic_to_nautobot.sync_nodes")
    @patch("understack_workflows.main.resync_ironic_to_nautobot.pynautobot")
    @patch("understack_workflows.main.resync_ironic_to_nautobot.credential")
    @patch("understack_workflows.main.resync_ironic_to_nautobot.setup_logger")
    @patch("understack_workflows.main.resync_ironic_to_nautobot.argument_parser")
    def test_main_with_failures(
        self, mock_parser, mock_logger, mock_cred, mock_pynb, mock_sync
    ):
        mock_args = MagicMock()
        mock_args.nautobot_token = "token"
        mock_args.nautobot_url = "http://nautobot"
        mock_args.node = None
        mock_args.dry_run = False
        mock_parser.return_value.parse_args.return_value = mock_args
        mock_sync.return_value = SyncResult(total=5, failed=2)

        result = main()

        assert result == 1
