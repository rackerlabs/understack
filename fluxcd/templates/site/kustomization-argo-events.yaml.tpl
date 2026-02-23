{{- if eq (include "fluxcd.isEnabled" (list $.Values.site "argo_events")) "true" }}
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {{ printf "%s-%s" $.Release.Name "argo-events" }}
  namespace: flux-system
spec:
  interval: 1h0s
  prune: {{ .Values.sync.prune }}
  sourceRef:
    kind: GitRepository
    name: understack
  path: components/argo-events
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "nautobot" }}
{{- end }}
