{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "global_workflows")) "true" }}
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {{ printf "%s-%s" $.Release.Name "global-workflows" }}
  namespace: flux-system
spec:
  interval: 1h0s
  prune: {{ .Values.sync.prune }}
  sourceRef:
    kind: GitRepository
    name: understack
  path: components/global-workflows
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "argo-workflows" }}
{{- end }}
