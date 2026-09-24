from ironic_understack.drivers.netdev_hardware import NetdevHardware


class PanosHardware(NetdevHardware):
    """Hardware type for PAN-OS (Palo Alto) network appliances.

    Behaves exactly like :class:`NetdevHardware` today. It exists as a distinct
    hardware type so a PAN-OS appliance is identifiable from the node's
    ``driver`` alone.
    """
