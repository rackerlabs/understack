from oslo_config import cfg

type_understack_opts = [
    cfg.StrOpt(
        "provisioning_network",
        help="provisioning_network ID as configured in ironic.conf",
    ),
    cfg.StrOpt(
        "argo_workflow_sa",
        default="workflow",
        help="ServiceAccount to submit Workflow as",
    ),
    cfg.StrOpt(
        "argo_api_url",
        default="https://argo-server.argo.svc.cluster.local:2746",
        help="URL of the Argo Server API",
    ),
    cfg.StrOpt(
        "argo_namespace",
        default="argo-events",
        help="Namespace to submit the Workflows to",
    ),
    cfg.IntOpt(
        "argo_max_attempts",
        default=15,
        help="Number of tries to retrieve the Workflow run result. "
        "Sleeps 5 seconds between attempts.",
    ),
    cfg.BoolOpt("argo_dry_run", default=True, help="Call Undersync with dry-run mode"),
    cfg.BoolOpt("argo_force", default=False, help="Call Undersync with force mode"),
]

mech_understack_opts = [
    cfg.StrOpt(
        "nb_url",
        help="Nautobot URL",
    ),
    cfg.StrOpt(
        "nb_token",
        help="Nautobot API token",
    ),
    cfg.StrOpt(
        "ucvni_group",
        help="hack",
    ),
]


def register_ml2_type_understack_opts(config):
    config.register_opts(type_understack_opts, "ml2_type_understack")


def register_ml2_understack_opts(config):
    config.register_opts(mech_understack_opts, "ml2_understack")
