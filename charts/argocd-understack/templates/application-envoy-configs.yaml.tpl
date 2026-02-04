{{- if or (eq (include "understack.isEnabled" (list $.Values.global "envoy_configs")) "true") (eq (include "understack.isEnabled" (list $.Values.site "envoy_configs")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "envoy-configs" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: envoy-gateway
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - path: components/envoy-configs
    helm:
      ignoreMissingValueFiles: true
      valueFiles:
      - $understack/components/envoy-configs/values.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/envoy-configs/values.yaml
    ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
  - path: {{ include "understack.deploy_path" $ }}/envoy-configs
    ref: deploy
    repoURL: {{ include "understack.deploy_url" $ }}
    targetRevision: {{ include "understack.deploy_ref" $ }}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    managedNamespaceMetadata:
      annotations:
        argocd.argoproj.io/sync-options: Delete=false
    syncOptions:
    - CreateNamespace=true
    - ServerSideApply=true
    - RespectIgnoreDifferences=true
    - ApplyOutOfSyncOnly=true
{{- end }}
