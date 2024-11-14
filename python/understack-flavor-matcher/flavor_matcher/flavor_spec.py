import os
from dataclasses import dataclass

import yaml

from flavor_matcher.machine import Machine


@dataclass
class PciSpec:
    vendor_id: str
    device_id: str
    sub_vendor_id: str
    sub_device_id: str


@dataclass
class FlavorSpec:
    name: str
    manufacturer: str
    model: str
    memory_gb: int
    cpu_cores: int
    cpu_model: str
    drives: list[int]
    pci: list[PciSpec]

    @staticmethod
    def from_yaml(yaml_str: str) -> "FlavorSpec":
        data = yaml.safe_load(yaml_str)
        return FlavorSpec(
            name=data["name"],
            manufacturer=data["manufacturer"],
            model=data["model"],
            memory_gb=data["memory_gb"],
            cpu_cores=data["cpu_cores"],
            cpu_model=data["cpu_model"],
            drives=data["drives"],
            pci=data.get("pci", []),
        )

    @property
    def stripped_name(self):
        """Returns actual flavor name with the prod/nonprod prefix removed."""
        _, name = self.name.split(".", 1)
        if not name:
            raise Exception(f"Unable to strip envtype from flavor: {self.name}")
        return name

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

    def score_machine(self, machine: Machine):
        # Scoring Rules:
        #
        # 1. 100% match gets highest priority, no further evaluation needed
        # 2. If the machine has less memory size than specified in the flavor,
        #    it cannot be used - the score should be 0.
        # 3. If the machine has smaller disk size than specified in the flavor,
        #    it cannot be used - the score should be 0.
        # 4. Machine must match the flavor on one of the CPU models exactly.
        # 5. If the machine has exact amount memory as specified in flavor, but
        #    more disk space it is less desirable than the machine that matches
        #    exactly on both disk and memory.
        # 6.  If the machine has exact amount of disk as specified in flavor,
        #     but more memory space it is less desirable than the machine that
        #     matches exactly on both disk and memory.

        # Rule 1: 100% match gets the highest priority
        if (
            machine.memory_gb == self.memory_gb
            and machine.disk_gb in self.drives
            and machine.cpu == self.cpu_model
        ):
            return 100

        # Rule 2: If machine has less memory than specified in the flavor, it cannot be used
        if machine.memory_gb < self.memory_gb:
            return 0

        # Rule 3: If machine has smaller disk than specified in the flavor, it cannot be used
        if any(machine.disk_gb < drive for drive in self.drives):
            return 0

        # Rule 4: Machine must match the flavor on one of the CPU models exactly
        if machine.cpu != self.cpu_model:
            return 0

        # Rule 5 and 6: Rank based on exact matches or excess capacity
        score = 0

        # Exact memory match gives preference
        if machine.memory_gb == self.memory_gb:
            score += 10
        elif machine.memory_gb > self.memory_gb:
            score += 5  # Less desirable but still usable

        # Exact disk match gives preference
        if machine.disk_gb in self.drives:
            score += 10
        elif all(machine.disk_gb > drive for drive in self.drives):
            score += 5  # Less desirable but still usable

        return score
