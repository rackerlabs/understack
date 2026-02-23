{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "nautobotop")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "nautobotop" }}
  namespace: nautobot
spec:
  interval: 1h0s
  releaseName: nautobot-operator
  chart:
    spec:
      chart: nautobot-operator
      version: 1.0.2
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: nautobot
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
