import logging
import os
import time

from flavor_matcher.flavor_spec import FlavorSpec
from watchdog.observers import Observer

from flavor_synchronizer import FlavorSynchronizer
from logger import setup_logger
from spec_changed_handler import SpecChangedHandler

loglevel = getattr(logging, os.getenv("NOVA_FLAVOR_MONITOR_LOGLEVEL", "info").upper())
logging.getLogger().setLevel(loglevel)
logger = setup_logger(__name__, level=loglevel)

# nonprod vs prod
FLAVORS_DIR = os.getenv("FLAVORS_DIR", "")
if not os.path.isdir(FLAVORS_DIR):
    raise ValueError(f"FLAVORS_DIR '{FLAVORS_DIR}' is not a directory")


def read_flavors():
    return FlavorSpec.from_directory(FLAVORS_DIR)


def main():
    synchronizer = FlavorSynchronizer(
        username=os.environ.get("OS_USERNAME", ""),
        password=os.environ.get("OS_PASSWORD", ""),
        project_id=os.environ.get("OS_PROJECT_ID"),
        user_domain_id=os.environ.get("OS_USER_DOMAIN_ID", ""),
        auth_url=os.environ.get("OS_AUTH_URL"),
    )

    handler = SpecChangedHandler(synchronizer, read_flavors)
    observer = Observer()
    observer.schedule(handler, FLAVORS_DIR, recursive=True)
    logger.info(f"Watching for changes in {FLAVORS_DIR}")
    observer.start()

    try:
        while True:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()

if __name__ == "__main__":
    main()
