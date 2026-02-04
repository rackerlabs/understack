# Configuring Dex

As of Dex v2.44.0 the HTTP 302 redirects contain a `Location` header which
is relative and not all clients like this in authentication flows. To workaround
this easiest approach is have the ingress rewrite the URL for us.

In `$DEPLOY_NAME/dex/values.yaml` in the `ingress.annotations` key, add the
following:

```yaml
ingress:
  annotations:
    nginx.ingress.kubernetes.io/proxy-redirect-from: "/"
    nginx.ingress.kubernetes.io/proxy-redirect-to: "https://dex.your.url/"
```
