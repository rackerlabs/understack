"""WSGI application and console-script entry point for kea_proxy."""

import sys

import pecan
from cheroot import wsgi
from ironic.common import service
from oslo_log import log as logging

from ironic_understack.conf import CONF
from ironic_understack.kea_proxy.controllers import RootController

LOG = logging.getLogger(__name__)


def make_app():
    return pecan.make_app(RootController(), debug=False)


def main():
    """Console-script entry point: `ironic-understack-kea-proxy`."""
    service.prepare_command(sys.argv[1:])

    app = make_app()
    bind_addr = (
        CONF.ironic_understack.kea_proxy_listen_host,
        CONF.ironic_understack.kea_proxy_listen_port,
    )
    server = wsgi.Server(bind_addr=bind_addr, wsgi_app=app, server_name="kea_proxy")

    LOG.info("Starting kea_proxy on %s:%s", *bind_addr)
    server.prepare()
    try:
        server.serve()
    finally:
        server.stop()


if __name__ == "__main__":
    main()
