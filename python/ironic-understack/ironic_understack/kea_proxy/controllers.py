"""REST controllers for the kea_proxy service."""

import pecan
from oslo_log import log as logging
from pecan import expose
from pecan import rest

from ironic_understack.kea_proxy import kea_client

LOG = logging.getLogger(__name__)


class ReservationsController(rest.RestController):
    @expose("json")
    def post(self):
        body = pecan.request.json
        hw_address = body.get("hw-address")
        client_class = body.get("client_class")
        if not hw_address or not client_class:
            pecan.response.status = 400
            return {"error": "hw-address and client_class are required"}

        try:
            kea_client.update_reservation(hw_address, client_class)
        except kea_client.KeaRequestError as e:
            LOG.error("Failed to update reservation for %s: %s", hw_address, e)
            pecan.response.status = 500
            return {"error": str(e)}

        return {"result": "ok"}


class LeasesController(rest.RestController):
    @expose("json")
    def get_all(self):
        mac = pecan.request.GET.get("mac")
        if not mac:
            pecan.response.status = 400
            return {"error": "mac query parameter is required"}

        return {"addresses": kea_client.get_leases(mac)}

    @expose("json")
    def delete(self):
        body = pecan.request.json
        hw_address = body.get("hw-address")
        if not hw_address:
            pecan.response.status = 400
            return {"error": "hw-address is required"}

        try:
            kea_client.delete_reservation(hw_address)
        except kea_client.KeaRequestError as e:
            LOG.error("Failed to delete reservation for %s: %s", hw_address, e)
            pecan.response.status = 500
            return {"error": str(e)}

        return {"result": "ok"}


class V1Controller:
    update_reservation = ReservationsController()
    leases = LeasesController()


class RootController:
    v1 = V1Controller()
