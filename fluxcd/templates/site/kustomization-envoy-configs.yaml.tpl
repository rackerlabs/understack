{{- if eq (include "fluxcd.isEnabled" (list $.Values.site "envoy_configs")) "true" }}
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {{ printf "%s-%s" $.Release.Name "envoy-configs" }}
  namespace: flux-system
spec:
  interval: 1h0s
  prune: {{ .Values.sync.prune }}
  sourceRef:
    kind: GitRepository
    name: deploy
  path: {{ include "fluxcd.deploy_path" $ }}/envoy-configs
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "envoy-gateway" }}
{{- end }}
