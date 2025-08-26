# Configuring OpenStack State

For information about state configuration, see
[Modifying Environment State](./component-config.md#modifying-environment-state).

The reference template to use for `$DEPLOY_NAME/manifests/openstack/configmap-understack.yaml`
is as follows:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: understack
data:
  # Is this a 'site' or a 'global' environment
  env_type: site
  # the URL where your dex instance is accessible
  dex_url: https://dex.url
