import logging
from pprint import pprint

from neutron.services.l3_router.l3_router_plugin import L3RouterPlugin
from neutron_lib.context import Context
from neutron_lib.db import resource_extend

LOG = logging.getLogger(__name__)


def print_context_and_pre_commit_data(
    method: str, context: Context, data: list
) -> None:
    context_for_print = context.to_dict()
    context_for_print.pop("auth_token")
    LOG.info("%s pre-commit method called with context:", method)
    pprint(context_for_print)
    pprint("PRE_COMMIT DATA:")
    pprint(data)


def print_post_commit_data(method: str, data: dict) -> None:
    LOG.info("%s post-commit method returned data:", method)
    pprint("POST_COMMIT DATA:")
    pprint(data)


@resource_extend.has_resource_extenders
class UnderStackL3ServicePlugin(L3RouterPlugin):
    """Understack L3 plugin.

    L3 plugin to deal with Understack infrastructure.
    """

    @classmethod
    def get_plugin_type(cls):
        return "L3_ROUTER_NAT"

    def get_plugin_description(self):
        return "Understack L3 Service Plugin"

    def create_router(self, context, router):
        method = "create_router"
        print_context_and_pre_commit_data(method, context, [router])
        router_dict = super().create_router(context, router)
        print_post_commit_data(method, router_dict)
        return router_dict

    def update_router(self, context, id, router):
        method = "update_router"
        print_context_and_pre_commit_data(method, context, [router, id])
        router_dict = super().update_router(context, id, router)
        print_post_commit_data(method, router_dict)
        return router_dict

    def delete_router(self, context, id):
        print_context_and_pre_commit_data("delete_router", context, [id])
        return super().delete_router(context, id)

    def add_router_interface(self, context, router_id, interface_info=None):
        method = "add_router_interface"
        print_context_and_pre_commit_data(method, context, [router_id, interface_info])
        return_data = super().add_router_interface(context, router_id, interface_info)
        print_post_commit_data(method, return_data)
        return return_data

    def remove_router_interface(self, context, router_id, interface_info):
        method = "remove_router_interface"
        print_context_and_pre_commit_data(method, context, [router_id, interface_info])
        return_data = super().remove_router_interface(
            context, router_id, interface_info
        )
        print_post_commit_data(method, return_data)
        return return_data

    def create_floatingip(self, context, floatingip):
        method = "create_floatingip"
        print_context_and_pre_commit_data(method, context, [floatingip])
        floatingip_dict = super().create_floatingip(context, floatingip)
        print_post_commit_data(method, floatingip_dict)
        return floatingip_dict

    def update_floatingip(self, context, id, floatingip):
        method = "update_floatingip"
        print_context_and_pre_commit_data(method, context, [id, floatingip])
        floatingip_dict = super().update_floatingip(context, id, floatingip)
        print_post_commit_data(method, floatingip_dict)
        return floatingip_dict

    def delete_floatingip(self, context, id):
        print_context_and_pre_commit_data("delete_floatingip", context, [id])
        return super().delete_floatingip(context, id)
