{{- if or (eq (include "understack.isEnabled" (list $.Values.global "otel_collector")) "true") (eq (include "understack.isEnabled" (list $.Values.site "otel_collector")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "otel-collector" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: otel-collector
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - path: {{ include "understack.deploy_path" $ }}/manifests/otel-collector
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
