# Operator Guide

This section aims to help users who have to support a running Understack.

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

## Infrastructure Topics

- [Gateway API Migration Guide](gateway-api.md) - Migration from ingress-nginx to Kubernetes Gateway API with Envoy Gateway
- [Argo Workflows](workflows.md) - Workflow orchestration and troubleshooting
- [Monitoring Stack](monitoring.md) - Prometheus and Grafana monitoring

[cli]: <../user-guide/openstack-cli.md>
