{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "ingress_nginx")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "ingress-nginx" }}
  namespace: ingress-nginx
spec:
  interval: 1h0s
  releaseName: ingress-nginx
  chart:
    spec:
      chart: ingress-nginx
      version: 4.10.0
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: ingress-nginx
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
{{- end }}
