import subprocess

from .nic import NIC


class NICList(list):
    def __init__(self, data=None) -> None:
        nic_data = data or self._esxi_nics()
        return super().__init__(NICList.parse(nic_data))

    @staticmethod
    def parse(data):
        output = []
        for line in data.split("\n"):
            if line.startswith("vmnic"):
                parts = line.split()
                nic = NIC(name=parts[0], status=parts[3], link=parts[4], mac=parts[7])
                output.append(nic)
        return output

    def _esxi_nics(self) -> str:
        return subprocess.run(  # noqa: S603
            [
                "/bin/esxcli",
                "network",
                "nic",
                "list",
            ],
            check=True,
            capture_output=True,
        ).stdout.decode()

    def find_by_mac(self, mac) -> NIC:
        return next(nic for nic in self if nic.mac == mac)
