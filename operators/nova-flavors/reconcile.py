from flavor_matcher.flavor_spec import FlavorSpec
from flavor_matcher.flavor_spec import os
from flavor_synchronizer import FlavorSynchronizer
from logger import setup_logger

logger = setup_logger(__name__)

# nonprod vs prod
flv_env = os.getenv("FLAVORS_ENV", "undefined")
all_flavors = FlavorSpec.from_directory(os.getenv("FLAVORS_DIR", ""))
defined_flavors = [flv for flv in all_flavors if flv.name.startswith(flv_env)]



synchronizer = FlavorSynchronizer(
    username=os.environ.get("OS_USERNAME", ""),
    password=os.environ.get("OS_PASSWORD", ""),
    project_id=os.environ.get("OS_PROJECT_ID"),
    user_domain_id=os.environ.get("OS_USER_DOMAIN_ID", ""),
    auth_url=os.environ.get("OS_AUTH_URL"),
)
synchronizer.reconcile(defined_flavors)

