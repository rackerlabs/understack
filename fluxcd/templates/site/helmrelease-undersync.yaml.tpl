{{- if eq (include "fluxcd.isEnabled" (list $.Values.site "undersync")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "undersync" }}
  namespace: undersync
spec:
  interval: 1h0s
  releaseName: undersync
  chart:
    spec:
      chart: undersync
      version: 0.1.0
      sourceRef:
        kind: GitRepository
        namespace: flux-system
        name: understack
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
