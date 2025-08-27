# Configuring Argo Workflows

## UI and API access

To allow UI and API access to Argo Workflows you must configure SSO and
the Ingress. To start, in your deployment repo under `$ENV_NAME/manifests/`
you must have a `argo-workflows` directory.

You can download the SSO configuration template and Ingress template from:

- <https://github.com/rackerlabs/understack/blob/main/components/argo-workflows/sso>
- <https://github.com/rackerlabs/understack/blob/main/components/argo-workflows/ingress.yaml>

And place them in the `argo-workflows` directory. And then adding `kustomization.yaml`
with the following:

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
- https://github.com/rackerlabs/understack.git//components/argo-workflows/?ref=$TAG_OR_main_OR_OTHER_REF
- ingress.yaml

configMapGenerator:
  - name: workflow-controller-configmap
    behavior: merge
    files:
      - sso
+```

At a minimum you will need to adjust the URLs in `ingress.yaml` to point to your
Argo Workflows server and update the `sso` file's `issuer` field to point to your
Dex instance and the `redirectUrl` to point back to your Argo Workflows ingress.
