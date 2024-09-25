from ironic_understack.machine import Machine


def test_memory_gb_property():
    # Test a machine with exactly 1 GB of memory
    machine = Machine(memory_mb=1024, cpu="x86", disk_gb=50)
    assert machine.memory_gb == 1

    # Test a machine with 2 GB of memory
    machine = Machine(memory_mb=2048, cpu="x86", disk_gb=50)
    assert machine.memory_gb == 2

    # Test a machine with non-exact GB memory (should floor the value)
    machine = Machine(memory_mb=3072, cpu="x86", disk_gb=50)
    assert machine.memory_gb == 3

    # Test a machine with less than 1 GB of memory
    machine = Machine(memory_mb=512, cpu="x86", disk_gb=50)
    assert machine.memory_gb == 0
