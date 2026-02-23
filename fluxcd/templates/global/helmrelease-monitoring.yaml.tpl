{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "monitoring")) "true" }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "prometheus-crd" }}
  namespace: monitoring
spec:
  interval: 1h0s
  releaseName: prometheus-operator-crds
  chart:
    spec:
      chart: prometheus-operator-crds
      version: 24.0.2
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: prometheus-crds
  install:
    createNamespace: true
  upgrade:
    createNamespace: true
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $.Release.Name "monitoring" }}
  namespace: monitoring
spec:
  interval: 1h0s
  releaseName: kube-prometheus-stack
  chart:
    spec:
      chart: kube-prometheus-stack
      version: 79.5.0
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: prometheus-community
  install:
    createNamespace: true
    remediation:
      retries: 3
  upgrade:
    createNamespace: true
    remediation:
      retries: 3
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "prometheus-crd" }}
{{- end }}
