# Helm charts

## understackdb

understackdb is a helm chart that deploys database related resources like `Users`,
`Grants` and `Databases` for Understack to operate.

### Requirements

- [mariadb-operator](https://github.com/mariadb-operator/mariadb-operator) must
be installed in the Kubernetes cluster. This chart deliberately does not
include the operator as an explicit dependency to allow installations in the
clusters where MariaDB operator is installed already.

### Documentation

[docs]: https://github.com/rackerlabs/understack/blob/main/helm-charts/understackdb/README.md

See [README.md][docs] or use `helm show values`.

### Chart development

If adding any new values into `values.yaml`, make sure that the documentation
is updated. This can be done in following ways:

- manually update the README.md (not recommended!)
- in `helm-charts` directory run `devbox run generate-docs` to update docs once
- for "live" updates and preview [in your browser](http://localhost:4242), run
`devbox run livedocs-understackdb`
