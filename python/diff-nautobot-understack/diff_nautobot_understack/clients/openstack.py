import openstack

from diff_nautobot_understack.settings import app_settings as settings


class API:
    def __init__(self):
        cloud_name = settings.os_cloud
        debug = settings.debug

        openstack.enable_logging(debug=debug)
        self.cloud_connection = openstack.connect(cloud=cloud_name)
