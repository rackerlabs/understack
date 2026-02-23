{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "sealed_secrets")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "sealed-secrets" }}
  namespace: sealed-secrets
spec:
  interval: 1h0s
  releaseName: sealed-secrets
  chart:
    spec:
      chart: sealed-secrets
      version: 2.2.0
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: sealed-secrets-controller
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
