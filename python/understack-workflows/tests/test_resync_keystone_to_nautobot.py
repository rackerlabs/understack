"""Tests for resync_keystone_to_nautobot module."""

from unittest.mock import MagicMock
from unittest.mock import patch

from understack_workflows.main.resync_keystone_to_nautobot import argument_parser
from understack_workflows.main.resync_keystone_to_nautobot import main
from understack_workflows.main.resync_keystone_to_nautobot import sync_projects
from understack_workflows.main.sync_keystone import is_domain
from understack_workflows.resync import SyncResult


class TestIsDomain:
    """Test cases for is_domain helper function."""

    def test_is_domain_true(self):
        project = MagicMock()
        project.is_domain = True
        assert is_domain(project) is True

    def test_is_domain_false(self):
        project = MagicMock()
        project.is_domain = False
        assert is_domain(project) is False

    def test_is_domain_missing_attr(self):
        project = MagicMock(spec=[])
        assert is_domain(project) is False


class TestArgumentParser:
    """Test cases for argument_parser function."""

    def test_default_args(self):
        parser = argument_parser()
        args = parser.parse_args([])
        assert args.project is None
        assert args.dry_run is False

    def test_project_arg(self):
        parser = argument_parser()
        args = parser.parse_args(["--project", "test-uuid"])
        assert args.project == "test-uuid"

    def test_dry_run_arg(self):
        parser = argument_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True


class TestSyncProjects:
    """Test cases for sync_projects function."""

    def test_sync_all_projects_success(self):
        conn = MagicMock()
        project1 = MagicMock(
            id="12345678-1234-5678-1234-567812345678",
            name="project-1",
            is_domain=False,
        )
        project2 = MagicMock(
            id="87654321-4321-8765-4321-876543218765",
            name="project-2",
            is_domain=False,
        )
        conn.identity.projects.return_value = [project1, project2]

        nautobot = MagicMock()

        with patch(
            "understack_workflows.main.resync_keystone_to_nautobot.handle_project_update"
        ) as mock_update:
            mock_update.return_value = 0
            result = sync_projects(conn, nautobot)

        assert result.total == 2
        assert result.failed == 0
        assert result.skipped == 0
        assert mock_update.call_count == 2

    def test_sync_single_project(self):
        conn = MagicMock()
        project = MagicMock(
            id="12345678-1234-5678-1234-567812345678",
            name="project-1",
            is_domain=False,
        )
        conn.identity.get_project.return_value = project

        nautobot = MagicMock()

        with patch(
            "understack_workflows.main.resync_keystone_to_nautobot.handle_project_update"
        ) as mock_update:
            mock_update.return_value = 0
            result = sync_projects(
                conn, nautobot, project_uuid="12345678-1234-5678-1234-567812345678"
            )

        assert result.total == 1
        assert result.failed == 0
        conn.identity.get_project.assert_called_once_with(
            "12345678-1234-5678-1234-567812345678"
        )

    def test_sync_with_failures(self):
        conn = MagicMock()
        project1 = MagicMock(
            id="12345678-1234-5678-1234-567812345678",
            name="project-1",
            is_domain=False,
        )
        project2 = MagicMock(
            id="87654321-4321-8765-4321-876543218765",
            name="project-2",
            is_domain=False,
        )
        conn.identity.projects.return_value = [project1, project2]

        nautobot = MagicMock()

        with patch(
            "understack_workflows.main.resync_keystone_to_nautobot.handle_project_update"
        ) as mock_update:
            mock_update.side_effect = [0, 1]  # First succeeds, second fails
            result = sync_projects(conn, nautobot)

        assert result.total == 2
        assert result.failed == 1
        assert result.succeeded == 1

    def test_sync_skips_domains(self):
        conn = MagicMock()
        project = MagicMock(
            id="12345678-1234-5678-1234-567812345678",
            name="project-1",
            is_domain=False,
        )
        domain = MagicMock(
            id="87654321-4321-8765-4321-876543218765",
            name="domain-1",
            is_domain=True,
        )
        conn.identity.projects.return_value = [project, domain]

        nautobot = MagicMock()

        with patch(
            "understack_workflows.main.resync_keystone_to_nautobot.handle_project_update"
        ) as mock_update:
            mock_update.return_value = 0
            result = sync_projects(conn, nautobot)

        assert result.total == 2
        assert result.skipped == 1
        assert result.succeeded == 1
        mock_update.assert_called_once()

    def test_dry_run_skips_sync(self):
        conn = MagicMock()
        project = MagicMock(id="uuid-1", name="project-1", is_domain=False)
        conn.identity.projects.return_value = [project]

        nautobot = MagicMock()

        with patch(
            "understack_workflows.main.resync_keystone_to_nautobot.handle_project_update"
        ) as mock_update:
            result = sync_projects(conn, nautobot, dry_run=True)

        assert result.total == 1
        assert result.failed == 0
        mock_update.assert_not_called()


class TestMain:
    """Test cases for main function."""

    @patch("understack_workflows.main.resync_keystone_to_nautobot.sync_projects")
    @patch("understack_workflows.main.resync_keystone_to_nautobot.get_nautobot_client")
    @patch("understack_workflows.main.resync_keystone_to_nautobot.get_openstack_client")
    @patch("understack_workflows.main.resync_keystone_to_nautobot.setup_logger")
    @patch("understack_workflows.main.resync_keystone_to_nautobot.argument_parser")
    def test_main_success(
        self, mock_parser, mock_logger, mock_get_os, mock_get_nb, mock_sync
    ):
        mock_args = MagicMock()
        mock_args.project = None
        mock_args.dry_run = False
        mock_parser.return_value.parse_args.return_value = mock_args
        mock_sync.return_value = SyncResult(total=5, failed=0)

        result = main()

        assert result == 0
        mock_get_os.assert_called_once_with()

    @patch("understack_workflows.main.resync_keystone_to_nautobot.sync_projects")
    @patch("understack_workflows.main.resync_keystone_to_nautobot.get_nautobot_client")
    @patch("understack_workflows.main.resync_keystone_to_nautobot.get_openstack_client")
    @patch("understack_workflows.main.resync_keystone_to_nautobot.setup_logger")
    @patch("understack_workflows.main.resync_keystone_to_nautobot.argument_parser")
    def test_main_with_failures(
        self, mock_parser, mock_logger, mock_get_os, mock_get_nb, mock_sync
    ):
        mock_args = MagicMock()
        mock_args.project = None
        mock_args.dry_run = False
        mock_parser.return_value.parse_args.return_value = mock_args
        mock_sync.return_value = SyncResult(total=5, failed=2)

        result = main()

        assert result == 1
