import logging
import os
import time

from flavor_matcher.flavor_spec import FlavorSpec
from watchdog.observers import Observer

from nova_flavors.flavor_synchronizer import FlavorSynchronizer
from nova_flavors.logger import setup_logger
from nova_flavors.spec_changed_handler import SpecChangedHandler

loglevel = getattr(logging, os.getenv("NOVA_FLAVOR_MONITOR_LOGLEVEL", "info").upper())
logging.getLogger().setLevel(loglevel)
logger = setup_logger(__name__, level=loglevel)


flavors_dir = ""


def read_flavors():
    return FlavorSpec.from_directory(flavors_dir)


def main():
    # nonprod vs prod
    flavors_dir = os.getenv("FLAVORS_DIR", "")
    if not os.path.isdir(flavors_dir):
        raise ValueError(f"flavors_dir '{flavors_dir}' is not a directory")
    synchronizer = FlavorSynchronizer(
        username=os.getenv("OS_USERNAME", ""),
        password=os.getenv("OS_PASSWORD", ""),
        project_name=os.getenv("OS_PROJECT_NAME", "admin"),
        project_domain_name=os.getenv("OS_PROJECT_DOMAIN_NAME", "default"),
        user_domain_name=os.getenv("OS_USER_DOMAIN_NAME", "service"),
        auth_url=os.getenv("OS_AUTH_URL"),
    )

    handler = SpecChangedHandler(synchronizer, read_flavors)
    observer = Observer()
    observer.schedule(handler, flavors_dir, recursive=True)
    logger.info(f"Watching for changes in {flavors_dir}")
    observer.start()

    try:
        while True:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
