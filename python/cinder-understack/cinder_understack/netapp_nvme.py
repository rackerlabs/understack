"""NetApp NVMe driver with Nova/Ironic connector compatibility.

Thin wrapper around the native NetApp NVMe driver that translates
the 'initiator' field from Nova/Ironic to the 'nqn' field expected
by the NetApp driver.
"""

from cinder.volume.drivers.netapp.dataontap.nvme_cmode import NetAppCmodeNVMeDriver


class NetAppNVMeDriver(NetAppCmodeNVMeDriver):
    """NetApp NVMe driver with Nova/Ironic connector compatibility.

    This minimal wrapper only translates connector['initiator'] to
    connector['nqn'] for compatibility with Nova/Ironic which send
    'initiator' instead of 'nqn'.

    All other functionality is provided by the native upstream driver.
    """

    def initialize_connection(self, volume, connector):
        """Initialize connection with connector field translation.

        Nova/Ironic send 'initiator' but NetApp driver expects 'nqn'.
        Translate if needed, then call upstream.
        """
        if "initiator" in connector and "nqn" not in connector:
            connector["nqn"] = connector["initiator"]

        return super().initialize_connection(volume, connector)
