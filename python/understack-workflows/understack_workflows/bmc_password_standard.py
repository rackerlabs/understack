import ipaddress
from base64 import b64encode
from hashlib import pbkdf2_hmac
from math import floor

PASSWORD_LENGTH = 20


def standard_password(ip_addr: str, master_key: str) -> str:
    """Return a password string for the given IP address.

    >>> standard_password("10.3.2.30", "ultra-secret string")
    'Vbyf7AFhiY2phtD1vcF0'
    """
    try:
        ipaddress.ip_address(ip_addr)
    except ValueError:
        raise ValueError(f"Need an IPv4 address, not '{ip_addr}'") from None

    if not master_key:
        raise ValueError("Missing/empty master_key!")

    return _password(master_key + ip_addr)


def _password(text: str) -> str:
    password_bits = PASSWORD_LENGTH * 6

    hash = pbkdf2_hmac(
        hash_name="sha256",
        password=bytes(text, "utf-8"),
        salt=b"NaCl",
        iterations=100000,
        dklen=floor(password_bits / 8),
    )
    return b64encode(hash).decode("utf8")
