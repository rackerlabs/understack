import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class CpuSpec:
    cores: int
    model: str


@dataclass
class MemorySpec:
    size: int  # MB


@dataclass
class DriveSpec:
    size: int  # GB


@dataclass
class InterfaceSpec:
    name: str
    type: str
    mgmt_only: bool = False


@dataclass
class PowerPortSpec:
    name: str
    type: str
    maximum_draw: int | None = None


@dataclass
class ResourceClass:
    name: str
    cpu: CpuSpec
    memory: MemorySpec
    drives: list[DriveSpec]
    nic_count: int


@dataclass
class DeviceType:
    class_: str  # Using class_ since class is a Python keyword
    manufacturer: str
    model: str
    u_height: float
    is_full_depth: bool
    resource_class: list[ResourceClass]
    interfaces: list[InterfaceSpec] | None = None
    power_ports: list[PowerPortSpec] | None = None

    @staticmethod
    def from_yaml(yaml_str: str) -> "DeviceType":
        data = yaml.safe_load(yaml_str)

        # Parse resource classes
        resource_classes = []
        for rc_data in data.get("resource_class", []):
            cpu = CpuSpec(cores=rc_data["cpu"]["cores"], model=rc_data["cpu"]["model"])
            memory = MemorySpec(size=rc_data["memory"]["size"])
            drives = [DriveSpec(size=d["size"]) for d in rc_data["drives"]]
            resource_classes.append(
                ResourceClass(
                    name=rc_data["name"],
                    cpu=cpu,
                    memory=memory,
                    drives=drives,
                    nic_count=rc_data["nic_count"],
                )
            )

        # Parse interfaces
        interfaces = None
        if "interfaces" in data:
            interfaces = [
                InterfaceSpec(
                    name=i["name"],
                    type=i["type"],
                    mgmt_only=i.get("mgmt_only", False),
                )
                for i in data["interfaces"]
            ]

        # Parse power ports
        power_ports = None
        if "power-ports" in data:
            power_ports = [
                PowerPortSpec(
                    name=p["name"],
                    type=p["type"],
                    maximum_draw=p.get("maximum_draw"),
                )
                for p in data["power-ports"]
            ]

        return DeviceType(
            class_=data["class"],
            manufacturer=data["manufacturer"],
            model=data["model"],
            u_height=data["u_height"],
            is_full_depth=data["is_full_depth"],
            resource_class=resource_classes,
            interfaces=interfaces,
            power_ports=power_ports,
        )

    @staticmethod
    def from_directory(data_dir: Path) -> list["DeviceType"]:
        """Load all device type definitions from a directory."""
        device_types = []
        if not data_dir.exists():
            return device_types

        for pattern in ("*.yaml", "*.yml"):
            for filepath in data_dir.rglob(pattern):
                try:
                    yaml_content = filepath.read_text()
                    device_type = DeviceType.from_yaml(yaml_content)
                    device_types.append(device_type)
                except yaml.YAMLError as e:
                    logger.error("Error parsing YAML file %s: %s", filepath.name, e)
                except Exception as e:
                    logger.error("Error processing file %s: %s", filepath.name, e)
        return device_types

    def get_resource_class(self, name: str) -> ResourceClass | None:
        """Get a specific resource class by name."""
        for rc in self.resource_class:
            if rc.name == name:
                return rc
        return None
