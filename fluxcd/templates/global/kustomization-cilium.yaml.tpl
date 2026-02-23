{{- if eq (include "fluxcd.isEnabled" (list $.Values.global "cilium")) "true" }}
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {{ printf "%s-%s" $.Release.Name "cilium" }}
  namespace: flux-system
spec:
  interval: 1h0s
  prune: {{ .Values.sync.prune }}
  sourceRef:
    kind: GitRepository
    name: deploy
  path: {{ include "fluxcd.deploy_path" $ }}/cilium
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "cert-manager" }}
{{- end }}
