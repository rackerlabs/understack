{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "dex")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "dex" }}
  namespace: dex
spec:
  interval: 1h0s
  releaseName: dex
  chart:
    spec:
      chart: dex
      version: 0.16.0
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: dex
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
