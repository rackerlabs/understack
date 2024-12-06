import pytest
import time
from unittest.mock import MagicMock
from nova_flavors.flavor_synchronizer import FlavorSynchronizer
from nova_flavors.spec_changed_handler import SpecChangedHandler
from watchdog.events import DirModifiedEvent, FileModifiedEvent


@pytest.fixture
def handler():
    synchronizer = MagicMock(spec=FlavorSynchronizer)
    flavors_cback = MagicMock()
    return SpecChangedHandler(synchronizer, flavors_cback)


def test_init(handler):
    assert handler.last_call is None
    assert handler.synchronizer is not None
    assert handler.flavors_cback is not None


def test_on_modified_dir(handler):
    event = DirModifiedEvent("/path/to/dir")
    handler.on_modified(event)
    handler.synchronizer.reconcile.assert_called_once_with(handler.flavors_cback())


def test_on_modified_file(handler):
    event = MagicMock(spec=FileModifiedEvent)
    handler.on_modified(event)
    handler.synchronizer.reconcile.assert_not_called()


def test_run_cool_down(handler):
    event = DirModifiedEvent("/path/to/dir")
    handler.last_call = time.time() - 29
    handler._run(event)
    handler.synchronizer.reconcile.assert_not_called()


def test_run_no_cool_down(handler):
    event = DirModifiedEvent("/path/to/dir")
    handler.last_call = time.time() - 31
    handler._run(event)
    handler.synchronizer.reconcile.assert_called_once_with(handler.flavors_cback())


def test_run_first_call(handler):
    event = DirModifiedEvent("/path/to/dir")
    handler._run(event)
    handler.synchronizer.reconcile.assert_called_once_with(handler.flavors_cback())


@pytest.mark.parametrize("last_call", [None, time.time() - 100])
def test_run_logging(handler, last_call, caplog):
    event = DirModifiedEvent("/path/to/dir")
    handler.last_call = last_call
    with caplog.at_level("INFO"):
        handler._run(event)
    assert "Flavors directory /path/to/dir has changed." in caplog.text
