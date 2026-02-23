{{- if eq (include "fluxcd.isEnabled" (list $.Values.site "argo_events_workflows")) "true" }}
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {{ printf "%s-%s" $.Release.Name "argo-events-workflows" }}
  namespace: flux-system
spec:
  interval: 1h0s
  prune: {{ .Values.sync.prune }}
  sourceRef:
    kind: GitRepository
    name: understack
  path: workflows/argo-events
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "argo-events" }}
{{- end }}
