{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "external_secrets")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "external-secrets" }}
  namespace: external-secrets
spec:
  interval: 1h0s
  releaseName: external-secrets
  chart:
    spec:
      chart: external-secrets
      version: 0.9.17
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: external-secrets
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
