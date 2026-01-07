{{- if eq (include "understack.isEnabled" (list $.Values.site "snmp_exporter")) "true" }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "snmp-exporter" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: monitoring
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - chart: prometheus-snmp-exporter
    helm:
      ignoreMissingValueFiles: true
      releaseName: prometheus-snmp-exporter
      valueFiles:
      - $deploy/{{ $.Release.Name }}/helm-configs/prometheus-snmp-exporter.yaml
    repoURL: https://prometheus-community.github.io/helm-charts
    targetRevision: 5.6.0
  - ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
  - ref: deploy
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
