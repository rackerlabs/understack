import pytest

from understack_workflows.main import enroll_netdev


def test_argument_parser_defaults_resource_class_to_generic():
    args = enroll_netdev.argument_parser().parse_args(
        [
            "--name",
            "leaf01",
            "--physical-network",
            "f20-1-network",
            "--ports",
            (
                '[{"label": "port1", "mac": "00:11:22:33:44:55", '
                '"switch": "s1", "intf": "e1"}]'
            ),
        ]
    )

    assert args.resource_class == "generic"
    assert args.external_cmdb_id == ""
    assert enroll_netdev.parse_ports_arg(args.ports) == [
        {
            "label": "port1",
            "mac": "00:11:22:33:44:55",
            "switch": "s1",
            "intf": "e1",
        }
    ]


def test_main_emits_node_uuid_only_after_success(mocker, tmp_path):
    output = tmp_path / "node-uuid"
    mocker.patch(
        "sys.argv",
        [
            "enroll-netdev",
            "--name",
            "leaf01",
            "--physical-network",
            "net",
            "--ports",
            "[]",
            "--node-uuid-output",
            str(output),
        ],
    )
    mocker.patch.object(enroll_netdev.helpers, "setup_logger")
    enroll = mocker.patch.object(enroll_netdev, "enroll", return_value="node-123")

    enroll_netdev.main()

    assert output.read_text() == "node-123\n"
    output.unlink()
    enroll.side_effect = RuntimeError("enrollment failed")
    with pytest.raises(RuntimeError, match="enrollment failed"):
        enroll_netdev.main()
    assert not output.exists()
