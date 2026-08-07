# Release Notes

These pages document **what an operator has to do** to move a deployment from
one version of UnderStack to another: required changes to your deployment
repository, new or removed secrets, one-time manual steps, and how to roll
back.

They are deliberately **not** a changelog. For the full list of merged pull
requests in a given tag, see the
[GitHub releases page](https://github.com/rackerlabs/understack/releases).

!!! tip "If you deploy from `main`"
    The default deployment model sets `understack_ref: HEAD`, so most
    deployments track `main` continuously rather than a tag. Read the
    [Unreleased section](v0.4.md#unreleased) of the current series page. It
    covers everything merged to `main` since the most recent tag, and it is
    updated in the same pull request as the change it describes.

## Series

| Series | Status |
| ------ | ------ |
| [v0.4.x](v0.4.md) | Current |

## How to read these pages

- There is one page per **minor** series. Each page lists versions
  newest-first.
- **Only versions that require operator action get a section.** Most do not, so
  most versions are absent from these pages. If a version has no section, it
  needed nothing beyond a normal resync.
- Each section states its **Impact** (`Action required` or `Informational`) and
  which cluster types it **applies to**.

## Pinning a version

To upgrade deliberately rather than continuously, pin `understack_ref` to a tag
in your cluster values file instead of leaving it at `HEAD`. See
[ArgoCD Application Management](../operator-guide/argocd-helm-chart.md) for the
full explanation of how refs are resolved.

```yaml title="$CLUSTER_NAME/deploy.yaml"
understack_ref: v0.4.26
```

## Related upgrade guides

Some upgrades are large enough to warrant a standalone guide. Release notes link
to these rather than duplicating them.

- [Gateway API Migration Guide](../operator-guide/gateway-api.md) — moving from
  ingress-nginx to Envoy Gateway.
- [MariaDB Operator Upgrade Runbook](../operator-guide/mariadb-upgrade-runbook.md)
  — upgrading the operator, with backup and restore steps.
