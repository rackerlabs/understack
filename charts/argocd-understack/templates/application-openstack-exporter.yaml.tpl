{{- if eq (include "understack.isEnabled" (list $.Values.site "openstack_exporter")) "true" }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "openstack-exporter" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: monitoring
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - chart: prometheus-openstack-exporter
    helm:
      ignoreMissingValueFiles: true
      releaseName: prometheus-openstack-exporter
      valueFiles:
      - $understack/components/openstack-exporter/values.yaml
      - $deploy/{{ $.Release.Name }}/helm-configs/openstack-exporter.yaml
    repoURL: registry.scs.community/openstack-exporter
    targetRevision: 0.4.5
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
