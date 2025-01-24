import os

import openstack

OS_CLOUD = os.environ.get("OS_CLOUD", "uc-dev-infra")


openstack.enable_logging(debug=True)


class API:
    def __init__(self):
        self.cloud_connection = openstack.connect(cloud=OS_CLOUD)
