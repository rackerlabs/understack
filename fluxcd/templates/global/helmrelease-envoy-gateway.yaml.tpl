{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "envoy_gateway")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "envoy-gateway" }}
  namespace: envoy-gateway
spec:
  interval: 1h0s
  releaseName: envoy-gateway
  chart:
    spec:
      chart: envoy-gateway
      version: 1.2.0
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: envoy-gateway
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
