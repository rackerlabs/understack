{{- if eq (include "fluxcd.isEnabled" (list $.Values.site "openstack_exporter")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "openstack-exporter" }}
  namespace: openstack
spec:
  interval: 1h0s
  releaseName: openstack-exporter
  chart:
    spec:
      chart: openstack-exporter
      version: 1.0.0
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: openstack-exporter
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "monitoring" }}
{{- end }}
