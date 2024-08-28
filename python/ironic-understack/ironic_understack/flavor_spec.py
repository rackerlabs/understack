import os
from dataclasses import dataclass

import yaml


@dataclass
class FlavorSpec:
    name: str
    memory_gb: int
    cpu_cores: int
    cpu_models: list[str]
    drives: list[int]
    devices: list[str]

    @staticmethod
    def from_yaml(yaml_str: str) -> "FlavorSpec":
        data = yaml.safe_load(yaml_str)
        return FlavorSpec(
            name=data["name"],
            memory_gb=data["memory_gb"],
            cpu_cores=data["cpu_cores"],
            cpu_models=data["cpu_models"],
            drives=data["drives"],
            devices=data["devices"],
        )

    @staticmethod
    def from_directory(directory: str = "/etc/flavors/") -> list["FlavorSpec"]:
        flavor_specs = []
        for root, _, files in os.walk(directory):
            for filename in files:
                if filename.endswith(".yaml") or filename.endswith(".yml"):
                    filepath = os.path.join(root, filename)
                    try:
                        with open(filepath, "r") as file:
                            yaml_content = file.read()
                            flavor_spec = FlavorSpec.from_yaml(yaml_content)
                            flavor_specs.append(flavor_spec)
                    except yaml.YAMLError as e:
                        print(f"Error parsing YAML file {filename}: {e}")
                    except Exception as e:
                        print(f"Error processing file {filename}: {e}")
        return flavor_specs
