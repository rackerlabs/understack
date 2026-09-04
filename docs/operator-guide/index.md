# Operations

This section is for people supporting a running UnderStack. It covers three
roles, and the navigation is grouped by which one you are in today:

- **System operators** supporting the deployment as a whole — *Troubleshooting
  and Architecture*, *OpenStack Services*, *Platform Services*, *Scripts and
  Tools*.
- **Data centre technicians** working on an individual machine —
  [Hardware](hardware.md).
- **Network operations** working on network configuration —
  [Networking](networking.md).

If something is broken right now, start at
[Troubleshooting](troubleshooting.md).

## Authenticating

While the [User Guide][cli] explains how to configure your [CLI][cli] for regular
projects, for operators most of the baremetal infrastructure lives in the `infra`
domain under the `baremetal` project. So you will need another authentication
setup. You can achieve this by adjusting `OS_` environment variables or you can
add a second entry into `clouds.yaml` and change `OS_CLOUD` appropriately.

```yaml title="$HOME/.config/openstack/clouds.yaml"
clouds:
  uc-prod-infra:
    auth_type: v3websso
    identity_provider: sso
    protocol: openid
    auth:
      auth_url: {{ config.extra.auth_url }}
      project_domain_name: infra
      project_name: baremetal
  uc-prod:
    auth_type: v3websso
    identity_provider: sso
    protocol: openid
    auth:
      auth_url: {{ config.extra.auth_url }}
      project_domain_name: Default
      project_name: myproject
```

In the above case `uc-prod-infra` would be the operator area while `uc-prod` would
be the regular project area.

## Upgrading

- [Release Notes](../release-notes/index.md) - What you have to do to move a
  deployment between versions. If you deploy from `main`, read the
  [Unreleased](../release-notes/unreleased.md) page.

## Platform Services

The services UnderStack runs alongside OpenStack. Full list in the navigation;
these are the ones people look for first:

- [ArgoCD Application Management](argocd-helm-chart.md) - Enabling components and
  pinning versions per cluster
- [Gateway API Migration Guide](gateway-api.md) - Migration from ingress-nginx to Kubernetes Gateway API with Envoy Gateway
- [Argo Workflows](workflows.md) - Workflow orchestration and troubleshooting
- [OpenStack to Nautobot Sync](openstack-nautobot-sync.md) - Event-driven sync and bulk resync operations
- [Monitoring Stack](monitoring.md) - Prometheus and Grafana monitoring

[cli]: <../user-guide/openstack-cli.md>
