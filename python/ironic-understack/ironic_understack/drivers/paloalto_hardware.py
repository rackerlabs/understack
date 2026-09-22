from ironic_understack.drivers.netdev_hardware import NetdevHardware


class PaloAltoHardware(NetdevHardware):
    """Hardware type for Palo Alto network appliances.

    Behaves exactly like :class:`NetdevHardware` today. It exists as a distinct
    hardware type so a Palo Alto appliance is identifiable from the node's
    ``driver`` alone.
    """
