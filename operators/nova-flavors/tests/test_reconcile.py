import logging
import os
import pytest
from unittest.mock import patch

from nova_flavors.reconcile import (
    FlavorSynchronizer,
    SpecChangedHandler,
    main,
)
from watchdog.observers import Observer


@pytest.fixture
def mock_logger(mocker):
    return mocker.Mock(spec=logging.Logger)


@pytest.mark.parametrize("return_value", [None, "/non/existent/directory"])
def test_flavors_dir_env_var_not_set(mocker, return_value):
    # Set up
    mocker.patch("os.getenv", return_value=return_value)
    if return_value == "/non/existent/directory":
        mocker.patch("os.path.isdir", return_value=False)

    # Execute and Verify
    with pytest.raises(Exception):
        main()


@patch.dict(
    "os.environ",
    {
        "FLAVORS_ENV": "testenv",
        "NOVA_FLAVOR_MONITOR_LOGLEVEL": "info",
        "FLAVORS_DIR": "/",
    },
)
def test_main_exception(mocker, mock_logger):
    # Set up
    mocker.patch("nova_flavors.reconcile.setup_logger", return_value=mock_logger)
    mock_flavor_synchronizer = mocker.Mock(spec=FlavorSynchronizer)
    mocker.patch(
        "nova_flavors.reconcile.FlavorSynchronizer",
        return_value=mock_flavor_synchronizer,
    )
    mock_spec_changed_handler = mocker.Mock(spec=SpecChangedHandler)
    mocker.patch(
        "nova_flavors.reconcile.SpecChangedHandler",
        return_value=mock_spec_changed_handler,
    )
    mock_observer = mocker.Mock(spec=Observer)
    mocker.patch("nova_flavors.reconcile.Observer", return_value=mock_observer)
    mocker.patch("time.sleep", side_effect=Exception("Mock exception"))

    # Execute
    with pytest.raises(Exception):
        main()

    # Verify
    mock_observer.schedule.assert_called_once()
    mock_observer.start.assert_called_once()
    mock_observer.stop.assert_called_once()
    mock_observer.join.assert_called_once()
