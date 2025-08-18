import os
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from netapp_ontap.error import NetAppRestError

from understack_workflows.main.netapp_create_svm import SVM_PROJECT_TAG
from understack_workflows.main.netapp_create_svm import KeystoneProject
from understack_workflows.main.netapp_create_svm import NetAppManager
from understack_workflows.main.netapp_create_svm import argument_parser
from understack_workflows.main.netapp_create_svm import do_action
from understack_workflows.main.netapp_create_svm import main


class TestNetAppManager:
    """Test cases for NetAppManager class."""

    @pytest.fixture
    def mock_config_file(self):
        """Create a temporary config file for testing."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname
netapp_login = test-user
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(config_content)
            f.flush()
            yield f.name
        os.unlink(f.name)

    @pytest.fixture
    def mock_args(self, mock_config_file):
        """Create mock arguments for testing."""
        args = MagicMock()
        args.project_id = "test-project-123"
        args.volume_size = "1TB"
        args.aggregate_name = "test-aggregate"
        args.config_file = mock_config_file
        args.debug = False
        return args

    @patch("understack_workflows.main.netapp_create_svm.config")
    @patch("understack_workflows.main.netapp_create_svm.HostConnection")
    def test_init_success(self, mock_host_connection, mock_config, mock_args):
        """Test successful NetAppManager initialization."""
        manager = NetAppManager(mock_args)

        assert manager.args == mock_args
        mock_host_connection.assert_called_once_with(
            "test-hostname", username="test-user", password="test-password"
        )

    def test_parse_ontap_config_success(self, mock_config_file, mock_args):
        """Test successful config parsing."""
        manager = NetAppManager.__new__(NetAppManager)
        result = manager.parse_ontap_config(mock_config_file)

        expected = {
            "hostname": "test-hostname",
            "username": "test-user",
            "password": "test-password",
        }
        assert result == expected

    def test_parse_ontap_config_file_not_found(self, mock_args):
        """Test config parsing when file doesn't exist."""
        manager = NetAppManager.__new__(NetAppManager)

        with pytest.raises(SystemExit) as exc_info:
            manager.parse_ontap_config("/nonexistent/path")

        assert exc_info.value.code == 1

    def test_parse_ontap_config_missing_section(self, mock_args):
        """Test config parsing with missing section."""
        config_content = """[wrong_section]
some_key = some_value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(config_content)
            f.flush()

            manager = NetAppManager.__new__(NetAppManager)

            with pytest.raises(SystemExit) as exc_info:
                manager.parse_ontap_config(f.name)

            assert exc_info.value.code == 1

        os.unlink(f.name)

    def test_parse_ontap_config_missing_option(self, mock_args):
        """Test config parsing with missing required option."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname
netapp_login = test-user
# missing netapp_password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(config_content)
            f.flush()

            manager = NetAppManager.__new__(NetAppManager)

            with pytest.raises(SystemExit) as exc_info:
                manager.parse_ontap_config(f.name)

            assert exc_info.value.code == 1

        os.unlink(f.name)

    @patch("understack_workflows.main.netapp_create_svm.config")
    @patch("understack_workflows.main.netapp_create_svm.HostConnection")
    @patch("understack_workflows.main.netapp_create_svm.Svm")
    def test_create_svm_success(
        self, mock_svm_class, mock_host_connection, mock_config, mock_args
    ):
        """Test successful SVM creation."""
        mock_svm_instance = MagicMock()
        mock_svm_instance.name = "os-test-project-123"
        mock_svm_class.return_value = mock_svm_instance

        manager = NetAppManager(mock_args)
        manager.create_svm(mock_args)

        mock_svm_class.assert_called_once_with(
            name="os-test-project-123",
            aggregates=[{"name": "test-aggregate"}],
            language="c.utf_8",
            root_volume={"name": "os-test-project-123_root", "security_style": "unix"},
            allowed_protocols=["nvme"],
            nvme={"enabled": True},
        )
        mock_svm_instance.post.assert_called_once()
        mock_svm_instance.get.assert_called_once()

    @patch("understack_workflows.main.netapp_create_svm.config")
    @patch("understack_workflows.main.netapp_create_svm.HostConnection")
    @patch("understack_workflows.main.netapp_create_svm.Svm")
    def test_create_svm_failure(
        self, mock_svm_class, mock_host_connection, mock_config, mock_args
    ):
        """Test SVM creation failure."""
        mock_svm_instance = MagicMock()
        mock_svm_instance.post.side_effect = NetAppRestError("Test error")
        mock_svm_class.return_value = mock_svm_instance

        manager = NetAppManager(mock_args)

        with pytest.raises(SystemExit) as exc_info:
            manager.create_svm(mock_args)

        assert exc_info.value.code == 1

    @patch("understack_workflows.main.netapp_create_svm.config")
    @patch("understack_workflows.main.netapp_create_svm.HostConnection")
    @patch("understack_workflows.main.netapp_create_svm.Volume")
    def test_create_volume_success(
        self, mock_volume_class, mock_host_connection, mock_config, mock_args
    ):
        """Test successful volume creation."""
        mock_volume_instance = MagicMock()
        mock_volume_class.return_value = mock_volume_instance

        manager = NetAppManager(mock_args)
        manager.create_volume(mock_args)

        mock_volume_class.assert_called_once_with(
            name="vol_test-project-123",
            svm={"name": "os-test-project-123"},
            aggregates=[{"name": "test-aggregate"}],
            size="1TB",
        )
        mock_volume_instance.post.assert_called_once()
        mock_volume_instance.get.assert_called_once()

    @patch("understack_workflows.main.netapp_create_svm.config")
    @patch("understack_workflows.main.netapp_create_svm.HostConnection")
    @patch("understack_workflows.main.netapp_create_svm.Volume")
    def test_create_volume_failure(
        self, mock_volume_class, mock_host_connection, mock_config, mock_args
    ):
        """Test volume creation failure."""
        mock_volume_instance = MagicMock()
        mock_volume_instance.post.side_effect = NetAppRestError("Test error")
        mock_volume_class.return_value = mock_volume_instance

        manager = NetAppManager(mock_args)

        with pytest.raises(SystemExit) as exc_info:
            manager.create_volume(mock_args)

        assert exc_info.value.code == 1

    @patch("understack_workflows.main.netapp_create_svm.config")
    @patch("understack_workflows.main.netapp_create_svm.HostConnection")
    def test_svm_name(self, mock_host_connection, mock_config, mock_args):
        """Test SVM name generation."""
        manager = NetAppManager(mock_args)
        assert manager._svm_name() == "os-test-project-123"

    @patch("understack_workflows.main.netapp_create_svm.config")
    @patch("understack_workflows.main.netapp_create_svm.HostConnection")
    def test_volume_name(self, mock_host_connection, mock_config, mock_args):
        """Test volume name generation."""
        manager = NetAppManager(mock_args)
        assert manager._volume_name() == "vol_test-project-123"


class TestKeystoneProject:
    """Test cases for KeystoneProject class."""

    def test_init(self):
        """Test KeystoneProject initialization."""
        kp = KeystoneProject()
        assert kp.conn is None

    @patch("understack_workflows.main.netapp_create_svm.openstack.connect")
    def test_connect_success(self, mock_connect):
        """Test successful connection to OpenStack."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        kp = KeystoneProject()
        kp.connect()

        assert kp.conn == mock_conn
        mock_connect.assert_called_once()

    @patch("understack_workflows.main.netapp_create_svm.openstack.connect")
    def test_project_tags_with_existing_connection(self, mock_connect):
        """Test getting project tags with existing connection."""
        mock_project = MagicMock()
        mock_project.tags = ["tag1", "tag2", SVM_PROJECT_TAG]

        mock_conn = MagicMock()
        mock_conn.identity.get_project.return_value = mock_project

        kp = KeystoneProject()
        kp.conn = mock_conn

        tags = kp.project_tags("test-project-id")

        assert tags == ["tag1", "tag2", SVM_PROJECT_TAG]
        mock_conn.identity.get_project.assert_called_once_with("test-project-id")
        mock_connect.assert_not_called()

    @patch("understack_workflows.main.netapp_create_svm.openstack.connect")
    def test_project_tags_without_connection(self, mock_connect):
        """Test getting project tags without existing connection."""
        mock_project = MagicMock()
        mock_project.tags = ["tag1", SVM_PROJECT_TAG]

        mock_conn = MagicMock()
        mock_conn.identity.get_project.return_value = mock_project
        mock_connect.return_value = mock_conn

        kp = KeystoneProject()

        tags = kp.project_tags("test-project-id")

        assert tags == ["tag1", SVM_PROJECT_TAG]
        mock_connect.assert_called_once()
        mock_conn.identity.get_project.assert_called_once_with("test-project-id")

    @patch("understack_workflows.main.netapp_create_svm.openstack.connect")
    def test_project_tags_no_tags_attribute(self, mock_connect):
        """Test getting project tags when project has no tags attribute."""
        mock_project = MagicMock()
        del mock_project.tags  # Remove tags attribute

        mock_conn = MagicMock()
        mock_conn.identity.get_project.return_value = mock_project
        mock_connect.return_value = mock_conn

        kp = KeystoneProject()

        tags = kp.project_tags("test-project-id")

        assert tags == []

    @patch("understack_workflows.main.netapp_create_svm.openstack.connect")
    def test_project_tags_connection_failure(self, mock_connect):
        """Test project tags when connection fails."""
        mock_connect.return_value = None

        kp = KeystoneProject()

        with pytest.raises(Exception, match="Unable to connect to Identity"):
            kp.project_tags("test-project-id")


class TestArgumentParser:
    """Test cases for argument parser."""

    def test_argument_parser_required_args(self):
        """Test argument parser with all required arguments."""
        parser = argument_parser()
        args = parser.parse_args(
            [
                "--project_id",
                "test-project",
                "--volume_size",
                "1TB",
                "--aggregate_name",
                "test-aggregate",
            ]
        )

        assert args.project_id == "test-project"
        assert args.volume_size == "1TB"
        assert args.aggregate_name == "test-aggregate"
        assert args.debug is False
        assert args.config_file == "/etc/netapp/config.ini"

    def test_argument_parser_with_optional_args(self):
        """Test argument parser with optional arguments."""
        parser = argument_parser()
        args = parser.parse_args(
            [
                "--project_id",
                "test-project",
                "--volume_size",
                "500GB",
                "--aggregate_name",
                "test-aggregate",
                "--debug",
                "--config_file",
                "/custom/path/config.ini",
            ]
        )

        assert args.project_id == "test-project"
        assert args.volume_size == "500GB"
        assert args.aggregate_name == "test-aggregate"
        assert args.debug is True
        assert args.config_file == "/custom/path/config.ini"

    def test_argument_parser_missing_required_args(self):
        """Test argument parser with missing required arguments."""
        parser = argument_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["--project_id", "test-project"])


class TestDoAction:
    """Test cases for do_action function."""

    def test_do_action_with_svm_tag(self):
        """Test do_action when project has SVM tag."""
        mock_args = MagicMock()
        mock_args.project_id = "test-project"

        mock_netapp_manager = MagicMock()
        mock_kp = MagicMock()
        mock_kp.project_tags.return_value = ["tag1", SVM_PROJECT_TAG, "tag2"]

        do_action(mock_args, mock_netapp_manager, mock_kp)

        mock_kp.project_tags.assert_called_once_with("test-project")
        mock_netapp_manager.create_svm.assert_called_once_with(mock_args)
        mock_netapp_manager.create_volume.assert_called_once_with(mock_args)

    def test_do_action_without_svm_tag(self):
        """Test do_action when project doesn't have SVM tag."""
        mock_args = MagicMock()
        mock_args.project_id = "test-project"

        mock_netapp_manager = MagicMock()
        mock_kp = MagicMock()
        mock_kp.project_tags.return_value = ["tag1", "tag2"]

        with pytest.raises(SystemExit) as exc_info:
            do_action(mock_args, mock_netapp_manager, mock_kp)

        assert exc_info.value.code == 0
        mock_kp.project_tags.assert_called_once_with("test-project")
        mock_netapp_manager.create_svm.assert_not_called()
        mock_netapp_manager.create_volume.assert_not_called()


class TestMain:
    """Test cases for main function."""

    @patch("understack_workflows.main.netapp_create_svm.do_action")
    @patch("understack_workflows.main.netapp_create_svm.KeystoneProject")
    @patch("understack_workflows.main.netapp_create_svm.NetAppManager")
    @patch("understack_workflows.main.netapp_create_svm.argument_parser")
    @patch("understack_workflows.main.netapp_create_svm.utils")
    @patch("understack_workflows.main.netapp_create_svm.logger")
    def test_main_with_debug(
        self,
        mock_logger,
        mock_utils,
        mock_parser,
        mock_netapp_manager_class,
        mock_keystone_class,
        mock_do_action,
    ):
        """Test main function with debug enabled."""
        mock_args = MagicMock()
        mock_args.debug = True
        mock_parser.return_value.parse_args.return_value = mock_args

        mock_netapp_manager = MagicMock()
        mock_netapp_manager_class.return_value = mock_netapp_manager

        mock_kp = MagicMock()
        mock_keystone_class.return_value = mock_kp

        main()

        assert mock_utils.DEBUG == 1
        mock_do_action.assert_called_once_with(mock_args, mock_netapp_manager, mock_kp)

    @patch("understack_workflows.main.netapp_create_svm.do_action")
    @patch("understack_workflows.main.netapp_create_svm.KeystoneProject")
    @patch("understack_workflows.main.netapp_create_svm.NetAppManager")
    @patch("understack_workflows.main.netapp_create_svm.argument_parser")
    @patch("understack_workflows.main.netapp_create_svm.utils")
    @patch("understack_workflows.main.netapp_create_svm.logging")
    def test_main_without_debug(
        self,
        mock_logging,
        mock_utils,
        mock_parser,
        mock_netapp_manager_class,
        mock_keystone_class,
        mock_do_action,
    ):
        """Test main function without debug."""
        mock_args = MagicMock()
        mock_args.debug = False
        mock_parser.return_value.parse_args.return_value = mock_args

        mock_netapp_manager = MagicMock()
        mock_netapp_manager_class.return_value = mock_netapp_manager

        mock_kp = MagicMock()
        mock_keystone_class.return_value = mock_kp

        main()

        mock_logging.getLogger.return_value.setLevel.assert_called_with(
            mock_logging.INFO
        )
        mock_do_action.assert_called_once_with(mock_args, mock_netapp_manager, mock_kp)
