import argparse
import os
from contextlib import nullcontext
from unittest.mock import patch

import pytest

from understack_workflows.helpers import parser_nautobot_args


@pytest.mark.parametrize(
    ("arg_list", "context", "expected_url"),
    [
        (["--nautobot_url", ""], pytest.raises(SystemExit), None),
        (["--nautobot_url", "http"], pytest.raises(SystemExit), None),
        (["--nautobot_url", "localhost"], pytest.raises(SystemExit), None),
        (["--nautobot_url", "http://localhost"], nullcontext(), "http://localhost"),
    ],
)
def test_parse_nautobot_url(arg_list, context, expected_url):
    with patch.dict(os.environ, {"NAUTOBOT_URL": "http://nautobot.example.com"}):
        parser = argparse.ArgumentParser()
        parser = parser_nautobot_args(parser)
        with context:
            args = parser.parse_args(arg_list)
            assert args.nautobot_url == expected_url


def test_parse_nautobot_url_from_env():
    """Test that NAUTOBOT_URL is read from environment variable."""
    with patch.dict(os.environ, {"NAUTOBOT_URL": "https://nautobot.example.com"}):
        parser = argparse.ArgumentParser()
        parser = parser_nautobot_args(parser)
        args = parser.parse_args([])
        assert args.nautobot_url == "https://nautobot.example.com"


def test_parse_nautobot_url_missing_env_raises():
    """Test that missing NAUTOBOT_URL environment variable raises ValueError."""
    with patch.dict(os.environ, {}, clear=True):
        # Remove NAUTOBOT_URL if it exists
        os.environ.pop("NAUTOBOT_URL", None)
        parser = argparse.ArgumentParser()
        with pytest.raises(
            ValueError, match="NAUTOBOT_URL environment variable must be set"
        ):
            parser_nautobot_args(parser)


@pytest.mark.parametrize(
    ("arg_list", "context", "expected_token"),
    [
        (["--nautobot_token", ""], nullcontext(), ""),
        (["--nautobot_token", "foo"], nullcontext(), "foo"),
        ([], nullcontext(), None),
    ],
)
def test_parse_nautobot_token(arg_list, context, expected_token):
    with patch.dict(os.environ, {"NAUTOBOT_URL": "http://nautobot.example.com"}):
        parser = argparse.ArgumentParser()
        parser = parser_nautobot_args(parser)
        with context:
            args = parser.parse_args(arg_list)
            assert args.nautobot_token == expected_token
