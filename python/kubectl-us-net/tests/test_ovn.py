from us_net.ovn import as_list
from us_net.ovn import nbctl_list_records
from us_net.ovn import parse_ovn_json


def test_parse_ovn_json_unwraps_uuid_and_set():
    raw = (
        '{"headings": ["_uuid", "ports"], '
        '"data": [[["uuid", "abc-123"], '
        '["set", [["uuid", "p1"], ["uuid", "p2"]]]]]}'
    )
    assert parse_ovn_json(raw) == [{"_uuid": "abc-123", "ports": ["p1", "p2"]}]


def test_parse_ovn_json_unwraps_map():
    raw = '{"headings": ["options"], "data": [[["map", [["chassis", "abc"]]]]]}'
    assert parse_ovn_json(raw) == [{"options": {"chassis": "abc"}}]


def test_parse_ovn_json_empty_set_stays_a_list():
    raw = '{"headings": ["ports"], "data": [[["set", []]]]}'
    assert parse_ovn_json(raw) == [{"ports": []}]


def test_as_list_normalizes_single_value_and_empty():
    assert as_list(None) == []
    assert as_list("") == []
    assert as_list("solo") == ["solo"]
    assert as_list(["a", "b"]) == ["a", "b"]


def test_nbctl_list_records_uses_if_exists(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "us_net.ovn.nbctl_raw",
        lambda ctx, args: calls.append(args) or '{"headings": [], "data": []}',
    )

    assert nbctl_list_records(None, "Logical_Router_Port", ["uuid-1"]) == []
    assert calls == [
        [
            "--format=json",
            "--if-exists",
            "list",
            "Logical_Router_Port",
            "uuid-1",
        ]
    ]
