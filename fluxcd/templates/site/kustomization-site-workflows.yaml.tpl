{{- if eq (include "fluxcd.isEnabled" (list $.Values.site "site_workflows")) "true" }}
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {{ printf "%s-%s" $.Release.Name "site-workflows" }}
  namespace: flux-system
spec:
  interval: 1h0s
  prune: {{ .Values.sync.prune }}
  sourceRef:
    kind: GitRepository
    name: understack
  path: components/site-workflows
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "argo-workflows" }}
    - name: {{ printf "%s-%s" $.Release.Name "argo-events" }}
{{- end }}
