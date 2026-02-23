{{- if eq (include "fluxcd.isEnabled" (list $.Values.site "openstack")) "true" }}
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {{ printf "%s-%s" $.Release.Name "openstack" }}
  namespace: flux-system
spec:
  interval: 1h0s
  prune: {{ .Values.sync.prune }}
  sourceRef:
    kind: GitRepository
    name: understack
  path: components/openstack
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "mariadb-operator" }}
    - name: {{ printf "%s-%s" $.Release.Name "rabbitmq-system" }}
    - name: {{ printf "%s-%s" $.Release.Name "openstack-memcached" }}
{{- end }}
