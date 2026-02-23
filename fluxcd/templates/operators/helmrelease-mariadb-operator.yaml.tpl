{{- if eq (include "fluxcd.isEnabled" (list $.Values.site "mariadb_operator")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "mariadb-operator" }}
  namespace: mariadb-operator
spec:
  interval: 1h0s
  releaseName: mariadb-operator
  chart:
    spec:
      chart: mariadb-operator
      version: 0.5.0
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: mariadb-operator
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
