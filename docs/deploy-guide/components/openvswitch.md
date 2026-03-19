# openvswitch

Open vSwitch networking backend.

## Deployment Scope

- Cluster scope: site
- Values key: `site.openvswitch`
- ArgoCD Application template: `charts/argocd-understack/templates/application-openvswitch.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  openvswitch:
    enabled: true
```

## How ArgoCD Builds It

- ArgoCD renders Helm chart `openvswitch`, Kustomize path `components/openvswitch/`.
- The shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files are loaded before the service-specific values file.
- The deploy repo contributes `values.yaml` for this component.
- The deploy repo overlay directory for this component is applied as a second source, so `kustomization.yaml` and any referenced manifests are part of the final Application.

## Deployment Repo Content

Use any secret delivery mechanism you prefer. The contract that matters is the final Kubernetes Secret or manifest shape described below.

Required or commonly required items:

- `values.yaml`: Provide the Open vSwitch chart overrides for host networking, offload, or DPDK behavior.
- `kustomization.yaml`: Include any site-specific manifests layered with the Open vSwitch deployment.

Optional additions:

- `Extra node-network manifests`: Add host or bridge-specific resources if the base chart is not sufficient.

## Notes

- This service is rendered by `application-openvswitch.yaml`, which also reads the shared site-level `secret-openstack.yaml` and optional `images-openstack.yaml` files before it reads `openvswitch/values.yaml`.
