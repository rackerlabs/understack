import time
from typing import Callable

from watchdog.events import DirModifiedEvent
from watchdog.events import FileModifiedEvent
from watchdog.events import FileSystemEventHandler

from nova_flavors.flavor_synchronizer import FlavorSynchronizer
from nova_flavors.logger import setup_logger

logger = setup_logger(__name__)


class SpecChangedHandler(FileSystemEventHandler):
    COOLDOWN_SECONDS = 30

    def __init__(
        self, synchronizer: FlavorSynchronizer, flavors_cback: Callable
    ) -> None:
        self.last_call = None
        self.synchronizer = synchronizer
        self.flavors_cback = flavors_cback

    def on_modified(self, event: DirModifiedEvent | FileModifiedEvent) -> None:
        if isinstance(event, DirModifiedEvent):
            self._run(event)

    def _run(self, event):
        now = time.time()
        if not self.last_call:
            self.last_call = now
        else:
            if self.last_call + self.COOLDOWN_SECONDS > now:
                logger.debug("Cooldown period.")
                return
        self.last_call = now
        logger.info(f"Flavors directory {event.src_path} has changed.")
        self.synchronizer.reconcile(self.flavors_cback())
