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
