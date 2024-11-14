from flavor_matcher.machine import Machine
from flavor_matcher.flavor_spec import FlavorSpec


class Matcher:
    def __init__(self, flavors: list[FlavorSpec]):
        self.flavors = flavors

    def match(self, machine: Machine) -> list[FlavorSpec]:
        """
        Find list of all flavors that the machine is eligible for.
        """
        results = []
        for flavor in self.flavors:
            score = flavor.score_machine(machine)
            if score > 0:
                results.append(flavor)
        return results

    def pick_best_flavor(self, machine: Machine) -> FlavorSpec | None:
        """
        Obtains list of all flavors that particular machine can be classified
        as, then tries to select "the best" one.
        """

        possible = self.match(machine)

        if len(possible) == 0:
            return None
        return max(possible, key=lambda flv: flv.memory_gb)
