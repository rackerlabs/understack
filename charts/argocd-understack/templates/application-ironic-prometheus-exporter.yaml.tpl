{{- if or (eq (include "understack.isEnabled" (list $.Values.global "ironic_prometheus_exporter")) "true") (eq (include "understack.isEnabled" (list $.Values.site "ironic_prometheus_exporter")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "ironic-prometheus-exporter" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: openstack
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - path: components/ironic-prometheus-exporter
    ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
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
