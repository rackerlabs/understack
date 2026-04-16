"""
An API to obtain data from Nautobot, and format it for use in various external
systems
"""

# Standard Library

# Third Party
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse

# First Party
from helpers.graphql import query_nautobot_graphql
from helpers.queries import OOB_TARGET_QUERY
from helpers.schemas import TargetResponse

app = FastAPI()


@app.exception_handler(Exception)
async def validation_exception_handler(request: Request, exc: Exception):
    """
    Generic catchall for exception handling
    """
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "path": str(request.url),
            "detail": f"Exception message is {exc!r}.",
        },
    )


@app.get("/targets/oob")
def get_oob_targets() -> list[TargetResponse]:
    """
    Obtains a list of targets to monitor from Nautobot, and returns them in a
    format that can be read by the Prometheus `http_sd_config` method.
    """
    response = query_nautobot_graphql(OOB_TARGET_QUERY).json()
    res = []
    for interface in response["data"]["interfaces"]:
        for device in interface["ip_addresses"]:
            urn = interface["device"].get("cpf_urn")
            # Only return devices which contain a urn.
            if not urn:
                continue
            device_name = interface["device"]["name"]
            device_uuid = interface["device"]["id"]
            location = interface["device"]["location"]["name"]
            rack = interface["device"]["rack"]["name"]
            res.append(
                {
                    "targets": [device["host"]],
                    "labels": {
                        "device_name": device_name,
                        "uuid": device_uuid,
                        "location": location,
                        "rack": rack,
                        "urn": urn,
                    },
                }
            )
    return res
