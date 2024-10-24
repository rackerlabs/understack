def parse_event(payload) -> (str, str, str):
    """Parse Nautobot webhook event data.

    Here we consume the event that Nautobot publishes whenever an ethernet
    interface is updated.  (Other types of event will raise an error)

    returns device_uuid: str, hostname: str, bmc_ip_address: str
    """
    data = payload.get("data")
    model = payload.get("model")

    if model not in ["interface"]:
        raise ValueError(f"'{model}' events not supported")

    device_uuid = data["device"]["id"]
    device_hostname = data["device"]["name"]
    bmc_ip_address = data["ip_addresses"][0]["host"]

    return device_uuid, device_hostname, bmc_ip_address
