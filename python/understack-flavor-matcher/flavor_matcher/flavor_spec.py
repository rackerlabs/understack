import os
import re
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

    @staticmethod
    def configured_envtype():
        return os.getenv("FLAVORS_ENV", "unconfigured")

    @property
    def stripped_name(self):
        """Returns actual flavor name with the prod/nonprod prefix removed."""
        _, name = self.name.split(".", 1)
        if not name:
            raise Exception(f"Unable to strip envtype from flavor: {self.name}")
        return name

    @property
    def baremetal_nova_resource_class(self):
        """Returns flavor name converted to be used with Nova flavor resources.

        https://docs.openstack.org/ironic/latest/install/configure-nova-flavors.html
        """
        converted_name = re.sub(r"[^\w]", "_", self.stripped_name).upper()
        return f"resources:CUSTOM_BAREMETAL_{converted_name}"

    @property
    def env_type(self):
        return self.name.split(".")[0]

    @property
    def memory_mib(self):
        """Returns memory size in MiB"""
        return self.memory_gb * 1024

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
                            if flavor_spec.env_type != FlavorSpec.configured_envtype():
                                continue
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
        # 4. If the machine's model does not match exactly, score should be 0
        # 5. Machine must match the flavor on one of the CPU models exactly.
        # 6. If the machine has exact amount memory as specified in flavor, but
        #    more disk space it is less desirable than the machine that matches
        #    exactly on both disk and memory.
        # 7.  If the machine has exact amount of disk as specified in flavor,
        #     but more memory space it is less desirable than the machine that
        #     matches exactly on both disk and memory.

        # Rule 1: 100% match gets the highest priority
        if (
            machine.memory_gb == self.memory_gb
            and machine.disk_gb in self.drives
            and machine.cpu == self.cpu_model
            and machine.model == self.model
        ):
            return 100

        # Rule 2: If machine has less memory than specified in the flavor, it cannot be used
        if machine.memory_gb < self.memory_gb:
            return 0

        # Rule 3: If machine has smaller disk than specified in the flavor, it cannot be used
        if any(machine.disk_gb < drive for drive in self.drives):
            return 0

        # Rule 4: Machine's model must match exactly
        if machine.model != self.model:
            return 0

        # Rule 5: Machine must match the flavor on one of the CPU models exactly
        if machine.cpu != self.cpu_model:
            return 0

        # Rule 6 and 7: Rank based on exact matches or excess capacity
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
