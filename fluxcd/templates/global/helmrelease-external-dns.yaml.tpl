{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "external_dns")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "external-dns" }}
  namespace: external-dns
spec:
  interval: 1h0s
  releaseName: external-dns
  chart:
    spec:
      chart: external-dns
      version: 1.14.1
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: external-dns
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
