from us_net.ovn import as_list
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
