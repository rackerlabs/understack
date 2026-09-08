# Contributing

This section is for people changing UnderStack itself, rather than deploying or
operating it.

!!! note "This front door is new and incomplete"
    Most contributor documentation still lives in `README.md` and
    `DEVELOPMENT.md` files next to the code. This page links to the main entry
    points until that material is consolidated here.

## Start here

- [RELEASING.md](https://github.com/rackerlabs/understack/blob/main/RELEASING.md)
  — how release notes and tags work. Read this before opening a pull request
  that changes anything an operator has to react to: such a pull request needs a
  `changelog.d/` fragment, and CI enforces it.
- [Adding and Removing an Application](../design-guide/add-remove-app.md) — how a
  component becomes an ArgoCD `Application`.
- [Design and Background](../openstack-helm.md) — why the project is shaped the
  way it is, starting with why we diverge from upstream OpenStack Helm.

## Development environments

Each language and package keeps its own setup instructions with the code. These
links open the current version on GitHub:

| Area | Entry points |
| --- | --- |
| Python packages | [Ironic][py-ironic], [Neutron][py-neutron], [Nova][py-nova], [workflows][py-workflows], [OpenStack sync][py-sync] |
| Go operators and CLIs | [understackctl][go-understackctl], [dexop][go-dexop], [nautobotop][go-nautobotop], [Ironic hardware exporter][go-ihe] |
| Helm charts | [ArgoCD UnderStack chart][chart-argocd], [site workflows][chart-workflows] |
| Ansible | [Playbooks and roles][ansible] |
| Containers | [Ironic][container-ironic], [Nautobot][container-nautobot], [Neutron][container-neutron], [Nova][container-nova] |
| End-to-end tests | [understack-tests][tests] |

Python packages use [uv](https://docs.astral.sh/uv/) with `pytest` and `ruff`;
Go projects use a `Makefile` with `golangci-lint`. Run the checks for the area
you touched before opening a pull request.

## Documentation

The site is built with [properdocs](https://github.com/rackerlabs/properdocs)
from `properdocs.yml`:

```bash
make docs-local   # build and serve on http://127.0.0.1:8001
make docs         # build with --strict, as CI does
```

Two things to know before you add a page:

- **Every page under `docs/` must appear in `nav:`.** `validation.omitted_files`
  plus `--strict` makes an unlisted page a build failure. There is no way to ship
  a page that is not in the navigation, which is deliberate — it is what keeps
  orphans out.
- **Some pages are generated**, and are gitignored rather than committed:
  `docs/workflows/` (from the Argo templates), the neutron sample config, and
  `docs/release-notes/unreleased.md` (from `changelog.d/`). Use `make docs`
  rather than calling `properdocs build` directly, or the generated pages will be
  missing and `--strict` will fail.

[py-ironic]: https://github.com/rackerlabs/understack/blob/main/python/ironic-understack/README.md
[py-neutron]: https://github.com/rackerlabs/understack/blob/main/python/neutron-understack/DEVELOPMENT.md
[py-nova]: https://github.com/rackerlabs/understack/blob/main/python/nova-understack/README.md
[py-workflows]: https://github.com/rackerlabs/understack/blob/main/python/understack-workflows/README.md
[py-sync]: https://github.com/rackerlabs/understack/blob/main/python/openstack-sync/README.md
[go-understackctl]: https://github.com/rackerlabs/understack/blob/main/go/understackctl/README.md
[go-dexop]: https://github.com/rackerlabs/understack/blob/main/go/dexop/README.md
[go-nautobotop]: https://github.com/rackerlabs/understack/blob/main/go/nautobotop/README.md
[go-ihe]: https://github.com/rackerlabs/understack/blob/main/go/ironic-hardware-exporter/README.md
[chart-argocd]: https://github.com/rackerlabs/understack/blob/main/charts/argocd-understack/README.md
[chart-workflows]: https://github.com/rackerlabs/understack/blob/main/charts/site-workflows/README.md
[ansible]: https://github.com/rackerlabs/understack/blob/main/ansible/README.md
[container-ironic]: https://github.com/rackerlabs/understack/blob/main/containers/ironic/README.md
[container-nautobot]: https://github.com/rackerlabs/understack/blob/main/containers/nautobot/README.md
[container-neutron]: https://github.com/rackerlabs/understack/blob/main/containers/neutron/README.md
[container-nova]: https://github.com/rackerlabs/understack/blob/main/containers/nova/README.md
[tests]: https://github.com/rackerlabs/understack/blob/main/python/understack-tests/README.md
