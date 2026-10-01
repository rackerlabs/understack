from unittest.mock import Mock

import pytest
from oslo_config import fixture as config_fixture

from ironic_understack.conf import CONF
from ironic_understack.utils import panos_api

KEY_OK = b'<response status="success"><result><key>KEY</key></result></response>'
BAD_CREDS = (
    b'<response status="error"><result><msg>Invalid Credential</msg></result>'
    b"</response>"
)
SYSTEM_INFO = b"""<response status="success"><result><system>
<hostname>fw-example</hostname>
<model>PA-1410</model>
<serial>000000000001</serial>
<sw-version>11.0.0</sw-version>
</system></result></response>"""


def _resp(status_code, content):
    return Mock(status_code=status_code, content=content)


@pytest.fixture
def conf():
    fixture = config_fixture.Config(CONF)
    fixture.setUp()
    fixture.config(
        standard_password="std",  # noqa: S106
        preconfig_password="pre",  # noqa: S106
        group="netdev_panos",
    )
    yield fixture
    fixture.cleanUp()


def _passwords_tried(session):
    return [c.kwargs["data"]["password"] for c in session.post.call_args_list]


def test_login_with_standard_password(conf):
    session = Mock()
    session.post.return_value = _resp(200, KEY_OK)
    client = panos_api.PanosClient("192.0.2.10", session=session)

    assert client.login() == "standard"
    assert client.api_key == "KEY"
    assert _passwords_tried(session) == ["std"]
    assert session.post.call_args.args == ("https://192.0.2.10/api/",)


def test_login_falls_back_in_order(conf):
    session = Mock()
    session.post.side_effect = [
        _resp(403, BAD_CREDS),
        _resp(403, BAD_CREDS),
        _resp(200, KEY_OK),
    ]
    client = panos_api.PanosClient("192.0.2.10", session=session)

    assert client.login() == "factory"
    # factory_password defaults to "admin"
    assert _passwords_tried(session) == ["std", "pre", "admin"]


def test_login_skips_unset_passwords(conf):
    conf.config(standard_password=None, group="netdev_panos")
    session = Mock()
    session.post.return_value = _resp(200, KEY_OK)
    client = panos_api.PanosClient("192.0.2.10", session=session)

    assert client.login() == "preconfig"
    assert _passwords_tried(session) == ["pre"]


def test_login_fails_when_every_password_is_rejected(conf):
    session = Mock()
    session.post.return_value = _resp(403, BAD_CREDS)
    client = panos_api.PanosClient("192.0.2.10", session=session)

    with pytest.raises(panos_api.PanosApiError, match="standard, preconfig, factory"):
        client.login()
    assert client.api_key is None


def test_login_fails_when_no_passwords_are_configured(conf):
    conf.config(
        standard_password=None,
        preconfig_password=None,
        factory_password=None,
        group="netdev_panos",
    )
    session = Mock()
    client = panos_api.PanosClient("192.0.2.10", session=session)

    with pytest.raises(panos_api.PanosApiError, match="no PAN-OS passwords"):
        client.login()
    session.post.assert_not_called()


def test_login_does_not_try_the_next_password_after_a_server_error(conf):
    # Only a 403 means the password was wrong; anything else is surfaced.
    session = Mock()
    session.post.return_value = _resp(500, b"<html>oops</html>")
    client = panos_api.PanosClient("192.0.2.10", session=session)

    with pytest.raises(panos_api.PanosApiError, match="HTTP 500"):
        client.login()
    assert session.post.call_count == 1


def test_verify_ssl_follows_config(conf):
    session = Mock()
    panos_api.PanosClient("192.0.2.10", session=session)
    assert session.verify is False

    conf.config(verify_ssl=True, group="netdev_panos")
    panos_api.PanosClient("192.0.2.10", session=session)
    assert session.verify is True


def test_system_info(conf):
    session = Mock()
    session.post.side_effect = [_resp(200, KEY_OK), _resp(200, SYSTEM_INFO)]
    client = panos_api.PanosClient("192.0.2.10", session=session)
    client.login()

    assert client.system_info() == {
        "hostname": "fw-example",
        "model": "PA-1410",
        "serial": "000000000001",
        "sw-version": "11.0.0",
    }
    assert session.post.call_args.kwargs["headers"] == {"X-PAN-KEY": "KEY"}


def test_op_requires_login(conf):
    client = panos_api.PanosClient("192.0.2.10", session=Mock())
    with pytest.raises(panos_api.PanosApiError, match="not logged in"):
        client.op("<show><system><info></info></system></show>")


def test_op_error_status_is_raised(conf):
    session = Mock()
    session.post.side_effect = [
        _resp(200, KEY_OK),
        _resp(
            200,
            b'<response status="error"><msg><line>bad command</line></msg></response>',
        ),
    ]
    client = panos_api.PanosClient("192.0.2.10", session=session)
    client.login()

    with pytest.raises(panos_api.PanosApiError, match="bad command"):
        client.op("<show><nope/></show>")
