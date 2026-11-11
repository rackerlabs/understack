from types import SimpleNamespace
from unittest.mock import MagicMock

from understack_workflows.ironic import client as client_module


def _client(mocker, pages):
    ironicclient = MagicMock()
    ironicclient.node.list.side_effect = pages
    mocker.patch.object(client_module, "get_ironic_client", return_value=ironicclient)
    return client_module.IronicClient(), ironicclient.node.list


def _nodes(*uuids):
    return [SimpleNamespace(uuid=uuid) for uuid in uuids]


def test_list_nodes_without_children_is_one_plain_request(mocker):
    client, node_list = _client(mocker, [_nodes("a", "b")])

    assert [n.uuid for n in client.list_nodes(driver="panos")] == ["a", "b"]
    node_list.assert_called_once_with(driver="panos")


def test_list_nodes_with_children_pages_by_marker(mocker):
    # Ironic's "next" link drops include_children, so every page must be a
    # fresh request that sends it again.
    client, node_list = _client(mocker, [_nodes("a", "b"), _nodes("c"), []])

    nodes = client.list_nodes(driver="panos", detail=True, include_children=True)

    assert [n.uuid for n in nodes] == ["a", "b", "c"]
    assert [call.kwargs for call in node_list.call_args_list] == [
        {"include_children": True, "marker": marker, "driver": "panos", "detail": True}
        for marker in (None, "b", "c")
    ]


def test_list_child_nodes_never_sends_include_children(mocker):
    # With include_children, Ironic ignores the parent_node filter.
    client, node_list = _client(mocker, [_nodes("child")])

    client.list_child_nodes("parent")

    node_list.assert_called_once_with(parent_node="parent", detail=True)
