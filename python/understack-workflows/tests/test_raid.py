import pytest

from understack_workflows.raid import PhysicalDisk
from understack_workflows.raid import _generate_raid_config
from understack_workflows.raid import _physical_disks_from_inventory


def raid_config_for_inventory(inventory: dict) -> dict:
    return _generate_raid_config(_physical_disks_from_inventory(inventory))


@pytest.fixture
def inventory_payload():
    return {
        "inventory": {
            "memory": {"physical_mb": 98304},
            "cpu": {
                "count": 32,
                "architecture": "x86_64",
                "model_name": "AMD EPYC 9124 16-Core Processor",
                "frequency": 4400,
            },
            "disks": [
                {"name": "Solid State Disk 0:1:0", "size": 479559942144},
                {"name": "Solid State Disk 0:1:1", "size": 479559942144},
            ],
            "storage_controllers": [
                {
                    "id": "RAID.SL.1-1",
                    "name": "PERC H755 Front",
                    "storage_controllers": [
                        {
                            "member_id": "0",
                            "name": "PERC H755 Front",
                            "raid_types": [
                                "RAID0",
                                "RAID1",
                                "RAID5",
                                "RAID6",
                                "RAID10",
                                "RAID50",
                                "RAID60",
                            ],
                            "speed_gbps": 12.0,
                            "controller_protocols": ["PCIe"],
                            "device_protocols": ["SAS", "SATA"],
                            "status": {"state": "Enabled"},
                        }
                    ],
                    "drives": [
                        {
                            "name": "Solid State Disk 0:1:0",
                            "size": 479559942144,
                            "id": "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                            "media_type": "SSD",
                            "serial_number": "234043C8E9AE",
                            "manufacturer": "MICRON",
                            "model": "MTFDDAK480TGA-1B",
                            "revision": "D4DK003",
                            "protocol": "SATA",
                            "status": {"state": "Enabled"},
                        },
                        {
                            "name": "Solid State Disk 0:1:1",
                            "size": 479559942144,
                            "id": "Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1",
                            "media_type": "SSD",
                            "serial_number": "234043C90EE1",
                            "manufacturer": "MICRON",
                            "model": "MTFDDAK480TGA-1B",
                            "revision": "D4DK003",
                            "protocol": "SATA",
                            "status": {"state": "Enabled"},
                        },
                    ],
                },
                {
                    "id": "AHCI.Embedded.1-1",
                    "name": "FCH SATA Controller [AHCI mode]",
                    "storage_controllers": [
                        {
                            "member_id": "0",
                            "name": "FCH SATA Controller [AHCI mode]",
                            "raid_types": [],
                            "speed_gbps": None,
                            "controller_protocols": ["PCIe"],
                            "device_protocols": [],
                            "status": {"state": "Enabled"},
                        }
                    ],
                    "drives": [],
                },
                {
                    "id": "CPU.1",
                    "name": "CPU.1",
                    "storage_controllers": [],
                    "drives": [],
                },
            ],
        },
        "plugin_data": {},
    }


def test_raid_config_from_inventory_payload(inventory_payload):
    assert raid_config_for_inventory(inventory_payload) == {
        "logical_disks": [
            {
                "controller": "RAID.SL.1-1",
                "physical_disks": [
                    "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                    "Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1",
                ],
                "raid_level": "1",
                "size_gb": "MAX",
                "is_root_volume": True,
            }
        ]
    }


def test_physical_disks_from_inventory_ignores_non_raid_controllers(inventory_payload):
    assert _physical_disks_from_inventory(inventory_payload) == {
        PhysicalDisk(
            id="Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
            controller="RAID.SL.1-1",
            size_gb=479,
        ),
        PhysicalDisk(
            id="Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1",
            controller="RAID.SL.1-1",
            size_gb=479,
        ),
    }


def test_raid_config_groups_disk_sizes_by_rounded_down_gb():
    assert raid_config_for_inventory(
        {
            "inventory": {
                "storage_controllers": [
                    {
                        "id": "RAID.SL.1-1",
                        "drives": [
                            {
                                "id": "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                                "size": 479559942144,
                            },
                            {
                                "id": "Disk.Bay.2:Enclosure.Internal.0-1:RAID.SL.1-1",
                                "size": 960000000000,
                            },
                            {
                                "id": "Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1",
                                "size": 479999999999,
                            },
                            {
                                "id": "Disk.Bay.3:Enclosure.Internal.0-1:RAID.SL.1-1",
                                "size": 960999999999,
                            },
                        ],
                    },
                ],
            },
        }
    ) == {
        "logical_disks": [
            {
                "controller": "RAID.SL.1-1",
                "physical_disks": [
                    "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                    "Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1",
                ],
                "raid_level": "1",
                "size_gb": "MAX",
                "is_root_volume": True,
            },
            {
                "controller": "RAID.SL.1-1",
                "physical_disks": [
                    "Disk.Bay.2:Enclosure.Internal.0-1:RAID.SL.1-1",
                    "Disk.Bay.3:Enclosure.Internal.0-1:RAID.SL.1-1",
                ],
                "raid_level": "1",
                "size_gb": "MAX",
                "is_root_volume": False,
            },
        ]
    }


def test_raid_config_sets_one_root_volume_across_all_controllers():
    assert raid_config_for_inventory(
        {
            "inventory": {
                "storage_controllers": [
                    {
                        "id": "RAID.SL.1-1",
                        "drives": [
                            {
                                "id": "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                                "size": 960000000000,
                            },
                        ],
                    },
                    {
                        "id": "RAID.SL.2-1",
                        "drives": [
                            {
                                "id": "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.2-1",
                                "size": 479559942144,
                            },
                        ],
                    },
                    {
                        "id": "RAID.SL.3-1",
                        "drives": [
                            {
                                "id": "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.3-1",
                                "size": 479999999999,
                            },
                        ],
                    },
                ],
            },
        }
    ) == {
        "logical_disks": [
            {
                "controller": "RAID.SL.2-1",
                "physical_disks": [
                    "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.2-1",
                ],
                "raid_level": "0",
                "size_gb": "MAX",
                "is_root_volume": True,
            },
            {
                "controller": "RAID.SL.3-1",
                "physical_disks": [
                    "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.3-1",
                ],
                "raid_level": "0",
                "size_gb": "MAX",
                "is_root_volume": False,
            },
            {
                "controller": "RAID.SL.1-1",
                "physical_disks": [
                    "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                ],
                "raid_level": "0",
                "size_gb": "MAX",
                "is_root_volume": False,
            },
        ]
    }


def test_raid_config_uses_raid0_for_one_drive():
    assert _generate_raid_config(
        {
            PhysicalDisk(
                id="Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                controller="RAID.SL.1-1",
                size_gb=479,
            )
        }
    ) == {
        "logical_disks": [
            {
                "controller": "RAID.SL.1-1",
                "physical_disks": [
                    "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                ],
                "raid_level": "0",
                "size_gb": "MAX",
                "is_root_volume": True,
            }
        ]
    }


def test_raid_config_uses_raid1_for_two_drives():
    assert _generate_raid_config(
        {
            PhysicalDisk(
                id="Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                controller="RAID.SL.1-1",
                size_gb=479,
            ),
            PhysicalDisk(
                id="Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1",
                controller="RAID.SL.1-1",
                size_gb=479,
            ),
        }
    ) == {
        "logical_disks": [
            {
                "controller": "RAID.SL.1-1",
                "physical_disks": [
                    "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                    "Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1",
                ],
                "raid_level": "1",
                "size_gb": "MAX",
                "is_root_volume": True,
            }
        ]
    }


def test_raid_config_uses_raid5_for_three_drives():
    assert _generate_raid_config(
        {
            PhysicalDisk(
                id="Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                controller="RAID.SL.1-1",
                size_gb=479,
            ),
            PhysicalDisk(
                id="Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1",
                controller="RAID.SL.1-1",
                size_gb=479,
            ),
            PhysicalDisk(
                id="Disk.Bay.2:Enclosure.Internal.0-1:RAID.SL.1-1",
                controller="RAID.SL.1-1",
                size_gb=479,
            ),
        }
    ) == {
        "logical_disks": [
            {
                "controller": "RAID.SL.1-1",
                "physical_disks": [
                    "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                    "Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1",
                    "Disk.Bay.2:Enclosure.Internal.0-1:RAID.SL.1-1",
                ],
                "raid_level": "5",
                "size_gb": "MAX",
                "is_root_volume": True,
            }
        ]
    }


def test_raid_config_uses_raid5_for_four_drives():
    assert _generate_raid_config(
        {
            PhysicalDisk(
                id="Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                controller="RAID.SL.1-1",
                size_gb=479,
            ),
            PhysicalDisk(
                id="Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1",
                controller="RAID.SL.1-1",
                size_gb=479,
            ),
            PhysicalDisk(
                id="Disk.Bay.2:Enclosure.Internal.0-1:RAID.SL.1-1",
                controller="RAID.SL.1-1",
                size_gb=479,
            ),
            PhysicalDisk(
                id="Disk.Bay.3:Enclosure.Internal.0-1:RAID.SL.1-1",
                controller="RAID.SL.1-1",
                size_gb=479,
            ),
        }
    ) == {
        "logical_disks": [
            {
                "controller": "RAID.SL.1-1",
                "physical_disks": [
                    "Disk.Bay.0:Enclosure.Internal.0-1:RAID.SL.1-1",
                    "Disk.Bay.1:Enclosure.Internal.0-1:RAID.SL.1-1",
                    "Disk.Bay.2:Enclosure.Internal.0-1:RAID.SL.1-1",
                    "Disk.Bay.3:Enclosure.Internal.0-1:RAID.SL.1-1",
                ],
                "raid_level": "5",
                "size_gb": "MAX",
                "is_root_volume": True,
            }
        ]
    }


def test_raid_config_is_empty_without_raid_disks():
    assert raid_config_for_inventory(
        {
            "inventory": {
                "storage_controllers": [
                    {
                        "id": "AHCI.Embedded.1-1",
                        "drives": [
                            {
                                "id": (
                                    "Disk.Bay.0:Enclosure.Internal.0-1"
                                    ":AHCI.Embedded.1-1"
                                ),
                                "size": 479559942144,
                            },
                        ],
                    },
                    {
                        "id": "CPU.1",
                        "drives": [],
                    },
                    {
                        "id": "RAID.SL.1-1",
                        "drives": [],
                    },
                ],
            },
        }
    ) == {"logical_disks": []}
