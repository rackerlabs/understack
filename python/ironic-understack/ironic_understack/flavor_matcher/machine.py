from dataclasses import dataclass


@dataclass
class Machine:
    memory_mb: int
    cpu: str
    cpu_cores: int
    disk_gb: int
    manufacturer: str
    model: str

    @property
    def memory_gb(self) -> int:
        return self.memory_mb // 1024
