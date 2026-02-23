{{- if eq (include "fluxcd.isEnabled" (list $.Values.site "openstack_memcached")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "openstack-memcached" }}
  namespace: openstack
spec:
  interval: 1h0s
  releaseName: memcached
  chart:
    spec:
      chart: memcached
      version: 6.8.0
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: bitnami
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
