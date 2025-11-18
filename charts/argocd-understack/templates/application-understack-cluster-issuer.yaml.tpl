{{- if or (eq (include "understack.isEnabled" (list $.Values.global "understack_cluster_issuer")) "true") (eq (include "understack.isEnabled" (list $.Values.site "understack_cluster_issuer")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "understack-cluster-issuer" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: cert-manager
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - path: {{ $.Release.Name }}/manifests/cert-manager
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
