from dataclasses import dataclass


@dataclass
class Machine:
    memory_mb: int
    cpu: str
    disk_gb: int
    model: str

    @property
    def memory_gb(self) -> int:
        return self.memory_mb // 1024
