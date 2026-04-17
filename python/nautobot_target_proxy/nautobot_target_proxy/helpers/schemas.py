# Third Party
from pydantic import BaseModel


class TargetResponse(BaseModel):
    labels: dict
    targets: list

    model_config = {
        "json_schema_extra": {
            "examples": [
                [
                    {
                        "labels": {
                            "location": "<datacenter>",
                            "name": "<dns_name>",
                        },
                        "targets": ["<host>"],
                    }
                ]
            ]
        }
    }
