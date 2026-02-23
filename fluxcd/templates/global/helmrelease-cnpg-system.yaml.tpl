{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "cnpg_system")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "cnpg-system" }}
  namespace: cnpg-system
spec:
  interval: 1h0s
  releaseName: cnpg-system
  chart:
    spec:
      chart: cloudnative-pg
      version: 1.22.1
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: cnpg-system
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
