import inspect
import logging
from urllib.parse import urljoin

import requests

from diff_nautobot_understack.settings import app_settings as settings


class API:
    CALLER_FRAME = 1

    def __init__(self):
        self.base_url = settings.nautobot_url
        self.s = requests.Session()
        self.token = settings.nautobot_token
        self.s.headers.update({"Authorization": f"Token {self.token}"})

    def make_api_request(
        self, url: str, payload: dict | None = None, paginated: bool = False
    ) -> dict | list:
        endpoint_url = urljoin(self.base_url, url)
        caller_function = inspect.stack()[self.CALLER_FRAME].function

        logging.debug(
            "%(caller_function)s payload: %(payload)s",
            {"payload": payload, "caller_function": caller_function},
        )

        if paginated:
            return self._fetch_paginated_data(endpoint_url, payload, caller_function)
        else:
            resp = self.s.get(endpoint_url, timeout=10, json=payload)
            return self._process_response(resp, caller_function)

    def _fetch_paginated_data(
        self, endpoint_url: str, payload: dict | None, caller_function: str
    ) -> list:
        response_items = []
        url = endpoint_url

        while url is not None:
            resp = self.s.get(url, timeout=10, json=payload)
            resp_data = self._process_response(resp, caller_function)

            response_items.extend(resp_data.get("results", []))
            url = resp_data.get("next")

        return response_items

    def _process_response(self, resp, caller_function: str) -> dict:
        if resp.content:
            resp_data = resp.json()
        else:
            resp_data = {"status_code": resp.status_code}

        logging.debug(
            "%(caller_function)s resp: %(resp)s",
            {"resp": resp_data, "caller_function": caller_function},
        )

        self._log_and_raise_for_status(resp)
        return resp_data

    def _log_and_raise_for_status(self, resp):
        try:
            resp.raise_for_status()
        except Exception as e:
            logging.error(f"HTTP error occurred: {e}")
            raise
