{{- if eq (include "fluxcd.isEnabled" (list $.Values.site "understack_cluster_issuer")) "true" }}
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {{ printf "%s-%s" $.Release.Name "understack-cluster-issuer" }}
  namespace: flux-system
spec:
  interval: 1h0s
  prune: {{ .Values.sync.prune }}
  sourceRef:
    kind: GitRepository
    name: deploy
  path: {{ include "fluxcd.deploy_path" $ }}/cluster-issuer
  dependsOn:
    - name: {{ printf "%s-%s" $.Release.Name "cert-manager" }}
{{- end }}
