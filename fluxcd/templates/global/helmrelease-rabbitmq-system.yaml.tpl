{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "rabbitmq_system")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "rabbitmq-system" }}
  namespace: rabbitmq-system
spec:
  interval: 1h0s
  releaseName: rabbitmq-cluster-operator
  chart:
    spec:
      chart: rabbitmq-cluster-operator
      version: 14.4.0
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: rabbitmq
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
