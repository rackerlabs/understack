{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "openebs")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "openebs" }}
  namespace: openebs
spec:
  interval: 1h0s
  releaseName: openebs
  chart:
    spec:
      chart: openebs
      version: 4.0.2
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: openebs
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
