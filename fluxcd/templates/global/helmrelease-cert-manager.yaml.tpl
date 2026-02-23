{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "cert_manager")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "cert-manager" }}
  namespace: cert-manager
spec:
  interval: 1h0s
  releaseName: cert-manager
  chart:
    spec:
      chart: cert-manager
      version: v1.16.1
      sourceRef:
        kind: HelmRepository
        name: jetstack
        namespace: flux-system
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
