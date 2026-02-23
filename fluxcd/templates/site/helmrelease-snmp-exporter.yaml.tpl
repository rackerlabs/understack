{{- if eq (include "fluxcd.isEnabled" (list $.Values.site "snmp_exporter")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "snmp-exporter" }}
  namespace: snmp-exporter
spec:
  interval: 1h0s
  releaseName: snmp-exporter
  chart:
    spec:
      chart: snmp-exporter
      version: 0.1.0
      sourceRef:
        kind: GitRepository
        namespace: flux-system
        name: understack
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "monitoring" }}
{{- end }}
