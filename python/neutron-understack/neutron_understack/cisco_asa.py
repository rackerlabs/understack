# Copyright (c) 2024 Rackspace Technology
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# This aims to provide a basic abstraction of Cisco ASA ASDM commands
# needed to support a basic router and floating IP. Anything more
# should really use ntc-templates

import ssl
from urllib.parse import quote_plus

import requests
import urllib3
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class _CustomHttpAdapter(requests.adapters.HTTPAdapter):
    """Custom adapter for bad ASA SSL."""

    def __init__(self, ssl_context=None, **kwargs):
        """Init to match requests HTTPAdapter."""
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = urllib3.poolmanager.PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=self.ssl_context,
        )


def _get_legacy_session():
    """Support bad ASA SSL."""
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = False
    ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
    session = requests.session()
    session.mount("https://", _CustomHttpAdapter(ctx))
    return session


def _cmd_str(cmds: list[str]) -> str:
    """Handles encoding of a list of commands to the URL string."""
    encoded_cmds = [quote_plus(cmd) for cmd in cmds]
    return "/".join(encoded_cmds)


class CiscoAsaAsdm:
    def __init__(
        self, mgmt_url: str, username: str, password: str, user_agent: str
    ) -> None:
        self.mgmt_url = mgmt_url
        self.s = _get_legacy_session()
        self.s.headers.update({"User-Agent": user_agent})
        self.s.auth = requests.auth.HTTPBasicAuth(username, password)
        self.s.verify = False  # these things are gross

    def _make_url(self, cmd_str: str) -> str:
        return f"{self.mgmt_url}/admin/exec/{cmd_str}"

    def _make_request(self, op: str, cmds: list[str]) -> bool:
        url = self._make_url(_cmd_str(cmds))
        LOG.debug("Cisco ASA ASDM request(%s): %s", op, url)
        try:
            r = self.s.get(url, timeout=20)
        except Exception:
            LOG.exception("Failed on %s", url)
            return False

        LOG.debug("ASA response: %d / %s", r.status_code, r.text)
        return True

    def create_nat(
        self,
        float_ip_addr: str,
        asa_outside_inf: str,
        inside_ip_addr: str,
        asa_inside_inf: str,
    ) -> bool:
        cmds = [
            f"object network OBJ-{inside_ip_addr}",
            f"host {inside_ip_addr}",
            f"nat ({asa_inside_inf},{asa_outside_inf}) static {float_ip_addr}",
        ]

        return self._make_request("create_nat", cmds)

    def delete_nat(self, inside_ip_addr: str) -> bool:
        cmds = [
            f"no object network OBJ-{inside_ip_addr}",
        ]

        return self._make_request("delete_nat", cmds)
