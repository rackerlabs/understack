# Creating the Deploy Repo

A deployment of UnderStack includes many different services, some of
which will require specific configuration about your environment such
as details about the hardware you will use or details on how you will
connect to the hardware.

These details will be accumulated in your Deployment Repository with
some data being shared while most being scoped to a
[Global cluster](./welcome.md#system-division) or
a [Site cluster](./welcome.md#system-division).

## Initial Structure

To begin we will create our directory structure inside our Deployment Repository.

```bash title="From the Deployment Repo"
# where 'my-global' is the environment name you've used for your global cluster
mkdir -p my-global/{manifests,helm-configs,inventory}
# where 'my-site' is the environment name you've used for your site cluster
mkdir -p my-site/{manifests,helm-configs,inventory}

cat <<- EOF > my-global/deploy.yaml
---
name: my-global
understack_url: https://github.com/rackerlabs/understack.git
understack_ref: v0.0.5  # replace with the tag or git reference you want to use
deploy_url: git@github.com:my-org/my-deploy.git
deploy_ref: HEAD
EOF

cat <<- EOF > my-site/deploy.yaml
---
name: my-site
understack_url: https://github.com/rackerlabs/understack.git
understack_ref: v0.0.5
deploy_url: git@github.com:my-org/my-deploy.git
deploy_ref: HEAD
EOF
```

For `dev` focused deployments, you do not need to specify the refs directly
as they can be set on the ArgoCD cluster secret to allow more flexibility
during testing.

### manifests directory

Inside of the `manifests` directory you'll create child directories that will
be named after each application that we will deploy. These directories are
expected to hold a `kustomization.yaml` as `kustomize` will be used to apply
these manifests to your cluster.

### helm-configs directory

The `helm-configs` directory holds YAML files which are Helm `values.yaml`
files that are used as additional values files that will be merged together
by Helm.

### inventory directory

This directory contains an Ansible inventory file along with Ansible
group_vars that are used as data by Ansible executions within the cluster
to configure different services

This directory contains an Ansible inventory file along with Ansible
group_vars that are used as data by Ansible executions within the cluster
to configure different services.
