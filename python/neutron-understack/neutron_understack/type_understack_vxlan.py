from neutron_lib import constants as p_const
from neutron_lib.plugins.ml2 import api
from oslo_log import log

LOG = log.getLogger(__name__)


class UnderstackVxlanTypeDriver(api.ML2TypeDriver):
    def __init__(self):
        """Understack based type driver."""
        super().__init__()
        LOG.info("ML2 Understack VXLAN Type initialization complete")

    def get_type(self):
        return p_const.TYPE_VXLAN

    def initialize(self):
        pass

    def initialize_network_segment_range_support(self):
        pass

    def update_network_segment_range_allocations(self):
        pass

    def get_network_segment_ranges(self):
        pass

    def is_partial_segment(self, segment):
        return False

    def validate_provider_segment(self, segment):
        pass

    def reserve_provider_segment(self, context, segment, filters=None):
        return segment

    def allocate_tenant_segment(self, context, filters=None):
        return {api.NETWORK_TYPE: p_const.TYPE_VXLAN}

    def release_segment(self, context, segment):
        pass

    def get_mtu(self, physical_network=None):
        pass
