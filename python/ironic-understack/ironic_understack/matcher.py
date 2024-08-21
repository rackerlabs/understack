from ironic_understack.machine import Machine
from ironic_understack.flavor_spec import FlavorSpec


class Matcher:
    def __init__(self, machines: list[Machine], flavors: list[FlavorSpec]):
        self.machines = machines
        self.flavors = flavors

    def score_machine_to_flavor(self, machine: Machine, flavor: FlavorSpec) -> int:
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
            machine.memory_gb == flavor.memory_gb and
            machine.disk_gb in flavor.drives and
            machine.cpu in flavor.cpu_models
        ):
            return 100

        # Rule 2: If machine has less memory than specified in the flavor, it cannot be used
        if machine.memory_gb < flavor.memory_gb:
            return 0

        # Rule 3: If machine has smaller disk than specified in the flavor, it cannot be used
        if any(machine.disk_gb < drive for drive in flavor.drives):
            return 0

        # Rule 4: Machine must match the flavor on one of the CPU models exactly
        if machine.cpu not in flavor.cpu_models:
            return 0

        # Rule 5 and 6: Rank based on exact matches or excess capacity
        score = 0

        # Exact memory match gives preference
        if machine.memory_gb == flavor.memory_gb:
            score += 10
        elif machine.memory_gb > flavor.memory_gb:
            score += 5  # Less desirable but still usable

        # Exact disk match gives preference
        if machine.disk_gb in flavor.drives:
            score += 10
        elif all(machine.disk_gb > drive for drive in flavor.drives):
            score += 5  # Less desirable but still usable

        return score

    def get_eligible_machines_for_flavor(self, flavor: FlavorSpec) -> list[Machine]:
        scored_machines = []

        for machine in self.machines:
            score = self.score_machine_to_flavor(machine, flavor)
            if score > 0:
                scored_machines.append((machine, score))

        # Sort machines by score, highest first
        scored_machines.sort(key=lambda x: x[1], reverse=True)

        # Return the machine objects, sorted by desirability
        return [machine for machine, _ in scored_machines]

    def match(self) -> dict[str, list[Machine]]:
        results = {}
        for flavor in self.flavors:
            eligible_machines = self.get_eligible_machines_for_flavor(flavor)
            results[flavor.name] = eligible_machines
        return results

