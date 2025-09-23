from nautobot_client import NautobotClient

import os

n = NautobotClient(
    api_key=os.getenv("NAUTOBOT_TOKEN"),
    base_url="https://nautobot.dev.undercloud.rackspace.net",
)
devices = n.get_device_interfaces("2f75cab3-63d7-45ad-9045-b80f44e86132")

print(devices)
print(n.generate_network_config(devices))
