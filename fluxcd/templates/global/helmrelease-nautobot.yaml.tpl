{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "nautobot")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "nautobot" }}
  namespace: nautobot
spec:
  interval: 1h0s
  releaseName: nautobot
  chart:
    spec:
      chart: nautobot
      version: 1.3.2
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: nautobot
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
