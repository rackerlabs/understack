import ipaddress
from base64 import b64encode
from hashlib import sha256

PASSWORD_LENGTH = 24


def standard_password(ip_addr: str, master_key: str) -> str:
    """Return a password string for the given IP address.

    >>> standard_password("10.3.2.30", "ultra-secret string")
    'DdushPf7IUTs6oya3ADS0OM3'
    """
    try:
        ipaddress.ip_address(ip_addr)
    except ValueError:
        raise ValueError(f"Need an IPv4 address, not '{ip_addr}'") from None

    if not master_key:
        raise ValueError("Missing/empty master_key!")

    long_password = _sha256_string(master_key + ip_addr)

    return long_password[:PASSWORD_LENGTH]


def _sha256_string(text: str) -> str:
    return b64encode(sha256(bytes(text, "utf-8")).digest()).decode("utf-8")
