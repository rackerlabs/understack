---
charts:
- components/understack-diagnostics
deploy_overrides:
  helm:
    mode: values_files
    paths:
    - understack-diagnostics/values.yaml
  kustomize:
    mode: second_source
---
# diagnostics

Receives diagnostic files that BMCs upload over HTTP and lets NodeDash read
them back. Each kind of file has its own top-level directory, named in the URL.
Dell SupportAssist collections use `supportassist`. A new kind needs no chart
change: the client uploads under a new name.

```text
iDRAC --PUT /diagnostics/<kind>/<node-uuid>/<file>--> internal gateway :80
        --> Service diagnostics :8080 --> /data/<kind>/<node-uuid>/<file>

NodeDash --GET https://diagnostics.<site>/archives/<kind>/<node-uuid>/ (basic auth)
        --> Service diagnostics :8081 --> /data/<kind>/<node-uuid>/
```

## Deployment Scope

- Cluster scope: site
- Values key: `site.understack_diagnostics`
- ArgoCD Application template: `charts/argocd-understack/templates/application-diagnostics.yaml`

## How to Enable

Set this component to enabled in your deployment values file:

```yaml title="$CLUSTER_NAME/deploy.yaml"
site:
  understack_diagnostics:
    enabled: true
```

## How ArgoCD Builds It

{{ component_argocd_builds() }}

## Deployment Repo Content

{{ secrets_disclaimer }}

Set these up for each site:

1. **Reader password.** In `$CLUSTER_NAME/understack-diagnostics/`, create
   the Secret `diagnostics-download-auth` with one key, `htpasswd`, holding
   an NGINX password file. The pod does not start without it.
2. **Upload route.** In `$CLUSTER_NAME/envoy-configs/`, add an HTTPRoute on
   the internal gateway that sends `PUT /diagnostics/` to Service
   `diagnostics` port `8080`. Allow long requests (15 minutes on iad3-dev).

    ```yaml
    apiVersion: gateway.networking.k8s.io/v1
    kind: HTTPRoute
    metadata:
      name: diagnostics-upload
      namespace: understack-diagnostics
    spec:
      parentRefs:
        - name: internal-gateway
          namespace: envoy-gateway
      rules:
        - matches:
            - path: {type: PathPrefix, value: /diagnostics/}
              method: PUT
          backendRefs:
            - {name: diagnostics, port: 8080}
          timeouts: {request: 15m, backendRequest: 15m}
    ```

3. **Read hostname.** In `$CLUSTER_NAME/envoy-configs/values.yaml`, add an
   `fqdn` entry that publishes Service `diagnostics` port `8081`.

    ```yaml
    - fqdn: diagnostics.<site>.undercloud.rackspace.net
      namespace: understack-diagnostics
      service:
        name: diagnostics
        port: 8081
    ```

4. **Ironic share URL (SupportAssist).** In `$CLUSTER_NAME/ironic/values.yaml`,
   set `conf.ironic.drac.support_assist_share_url` to
   `http://<internal gateway IP>/diagnostics/supportassist/{node_uuid}/`. Use
   the IP, not a hostname: many iDRACs have no DNS servers configured.
5. **NodeDash (SupportAssist).** Set `SUPPORT_ASSIST_ARCHIVE_URL` to
   `https://diagnostics.<site>.undercloud.rackspace.net/archives/supportassist/`
   and give NodeDash the reader username and password.

Optional: `$CLUSTER_NAME/understack-diagnostics/values.yaml` with
`storageClassName` (default `openebs-lvm`) and `storageSize` (default `40Gi`).

## Behavior

- **Uploads** need no credentials. A NetworkPolicy lets only the
  `envoy-gateway` namespace reach the pods, so anything that can reach the
  internal route can upload or overwrite a file of any kind. Never expose that
  route externally. Only `PUT` under `/diagnostics/` is accepted. It needs a
  `Content-Length`, rejects query strings and allows up to 2 GiB.
- **Reads** need the reader password and allow only GET and HEAD. One
  credential reads every file of every kind, so keep it in NodeDash and away
  from browsers.
- **Rollouts** use `Recreate` because the volume is `ReadWriteOnce`. Uploads
  fail briefly while the pod restarts. BMC export jobs can be retried.

## Storage and retention

Files are never deleted automatically, and uploads fail when the volume is
full. The volume is kept when the Argo CD app is removed; delete the
PersistentVolumeClaim by hand to release the storage. Check free space:

```sh
kubectl -n understack-diagnostics exec deploy/diagnostics -- df -h /data
```

To list, copy or delete files, see the
[diagnostics archives](../../operator-guide/diagnostics-archives.md)
operator guide.
