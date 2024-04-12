# nautobot

The helm chart for nautobot doesn't actually support taking secrets in by reference.
Instead they're read from the active cluster when supplied by reference which
there might not be access for. <https://github.com/nautobot/helm-charts/pull/356>
has been opened to attempt to address this but without it being merged, kustomize's
helm support can't consume it directly so the chart is templated out and committed
here.

The following commmands were run using <https://github.com/cardoe/helm-charts/tree/password-ref>
from the top level of this repo:

```bash
helm template \
    --namespace nautobot \
    nautobot \
    /path/to/nautobot/helm-charts/charts/nautobot \
    --skip-tests \
    -f components/nautobot/values.yaml \
    --output-dir components/nautobot/base
# we do secrets separately
rm -f components/nautobot/base/nautobot/templates/secret.yaml
cd components/nautobot/base
kustomize create --autodetect --recursive
cd ../../..
```
