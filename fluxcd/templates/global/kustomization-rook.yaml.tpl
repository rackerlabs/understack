{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "rook")) "true" }}
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {{ printf "%s-%s" $.Release.Name "rook" }}
  namespace: flux-system
spec:
  interval: 1h0s
  prune: {{ .Values.sync.prune }}
  sourceRef:
    kind: GitRepository
    name: understack
  path: {{ .Values.deploy_path_prefix }}/rook
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "cert-manager" }}
{{- end }}
