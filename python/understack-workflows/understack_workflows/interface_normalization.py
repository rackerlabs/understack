import re

ABBREVIATIONS = {
    "bundle-e": "Bundle-Ether",
    "be": "Bundle-Ether",
    "e": "Ethernet",
    "fa": "FastEthernet",
    "four": "FourHundredGigE",
    "fo": "FortyGigabitEthernet",
    "gi": "GigabitEthernet",
    "hu": "HundredGigE",
    "te": "TenGigabitEthernet",
    "tw": "TwentyFiveGigE",
}


def normalize_interface_name(name: str) -> str:
    lower_case_name = name.lower()

    for abbreviation, full_prefix in ABBREVIATIONS.items():
        if lower_case_name.startswith(abbreviation):
            return re.sub(r"^[a-zA-Z-]*", full_prefix, name)

    return name
