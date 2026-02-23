{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "openstack_resource_controller")) "true" }}
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {{ printf "%s-%s" $.Release.Name "openstack-resource-controller" }}
  namespace: flux-system
spec:
  interval: 1h0s
  prune: {{ .Values.sync.prune }}
  sourceRef:
    kind: GitRepository
    name: understack
  path: components/openstack
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "nautobot" }}
    - name: {{ printf "%s-%s" $.Release.Name "nautobotop" }}
{{- end }}
