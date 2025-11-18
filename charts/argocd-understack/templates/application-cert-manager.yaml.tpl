{{- if or (eq (include "understack.isEnabled" (list $.Values.global "cert_manager")) "true") (eq (include "understack.isEnabled" (list $.Values.site "cert_manager")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "cert-manager" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: cert-manager
    server: {{ $.Values.cluster_server }}
  project: understack-infra
  sources:
  - chart: cert-manager
    helm:
      releaseName: cert-manager
      valuesObject:
        crds:
          enabled: true
    repoURL: https://charts.jetstack.io
    targetRevision: 1.18.2
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
