{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "opentelemetry_operator")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "opentelemetry-operator" }}
  namespace: opentelemetry-operator
spec:
  interval: 1h0s
  releaseName: opentelemetry-operator
  chart:
    spec:
      chart: opentelemetry-operator
      version: 0.4.1
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: opentelemetry
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
