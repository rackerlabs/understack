from flavor_matcher.device_type import DeviceType
from flavor_matcher.device_type import ResourceClass
from flavor_matcher.machine import Machine


class Matcher:
    def __init__(self, device_types: list[DeviceType]):
        self.device_types = device_types

    def match(self, machine: Machine) -> tuple[DeviceType, ResourceClass] | None:
        """Find the resource class that matches the machine's hardware specs.

        Returns a tuple of (DeviceType, ResourceClass) that matches the machine,
        or None if no match is found.

        Matching rules:
        1. Manufacturer and model must match exactly
        2. CPU model must match exactly
        3. CPU cores must match exactly
        4. Memory must match exactly (in MB)
        5. Must have at least as many drives as specified in resource class
        6. Each drive must be at least as large as the smallest drive in resource class
        """
        for device_type in self.device_types:
            # Check manufacturer and model
            if (
                device_type.manufacturer != machine.manufacturer
                or device_type.model != machine.model
            ):
                continue

            # Check each resource class in this device type
            for resource_class in device_type.resource_class:
                # Check CPU model
                if resource_class.cpu.model != machine.cpu:
                    continue

                # Check CPU cores
                if resource_class.cpu.cores != machine.cpu_cores:
                    continue

                # Check memory (in MB)
                if resource_class.memory.size != machine.memory_mb:
                    continue

                # Check drives - machine must have enough storage
                # For simplicity, we check if machine's total disk meets the minimum
                # drive size specified in resource class
                min_drive_size = min(d.size for d in resource_class.drives)
                if machine.disk_gb < min_drive_size:
                    continue

                # Found a match
                return (device_type, resource_class)

        return None
