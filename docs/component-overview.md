# Overview

Understack is deployed as a collection of multiple applications and/or tools which
are referred to in the code base in different category groupings. Each of these
groupings can themselves be multiple applications combined.

## Adding an application

To add an application, you must perform the following steps.

1. Determine how its deployed. For example as a set of manifests or via [Helm][helm].

1. Create a directory that matches the namespace that you want to
   deploy to in either `components/` or `operators/`. Populating it with a
   `kustomization.yaml` or a `values.yaml` or both depending on the proper
   deployment.

1. Edit one of the following:

     - `apps/appset/infra.yaml`
     - `apps/appset/operators.yaml`
     - `apps/appset/components.yaml`

     Adding an entry into the list of components as appropriate for the way
     the application is deployed. You can use the existing ones as an example
     which can be followed.

1. Edit `scripts/gitopts-secrets-gen.sh` to create a directory and generate any
   secrets which the application may require.

[helm]: <https://helm.sh>
