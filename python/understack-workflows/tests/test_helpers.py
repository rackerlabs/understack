import argparse
from contextlib import nullcontext

import pytest

from understack_workflows.helpers import parser_nautobot_args


@pytest.mark.parametrize(
    "arg_list,context,expected_url",
    [
        (["--nautobot_url", ""], pytest.raises(SystemExit), None),
        (["--nautobot_url", "http"], pytest.raises(SystemExit), None),
        (["--nautobot_url", "localhost"], pytest.raises(SystemExit), None),
        (["--nautobot_url", "http://localhost"], nullcontext(), "http://localhost"),
        ([], nullcontext(), "http://nautobot-default.nautobot.svc.cluster.local"),
    ],
)
def test_parse_nautobot_url(arg_list, context, expected_url):
    parser = argparse.ArgumentParser()
    parser = parser_nautobot_args(parser)
    with context:
        args = parser.parse_args(arg_list)
        assert args.nautobot_url == expected_url


@pytest.mark.parametrize(
    "arg_list,context,expected_token",
    [
        (["--nautobot_token", ""], nullcontext(), ""),
        (["--nautobot_token", "foo"], nullcontext(), "foo"),
        ([], nullcontext(), None),
    ],
)
def test_parse_nautobot_token(arg_list, context, expected_token):
    parser = argparse.ArgumentParser()
    parser = parser_nautobot_args(parser)
    with context:
        args = parser.parse_args(arg_list)
        assert args.nautobot_token == expected_token
