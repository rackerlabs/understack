{{- if eq (include "understack.isEnabled" (list $.Values.site "openstack_memcached")) "true" }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "openstack-memcached" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: openstack
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - chart: memcached
    helm:
      ignoreMissingValueFiles: true
      releaseName: memcached
      valueFiles:
      - $understack/components/openstack/memcached-values.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/helm-configs/openstack-memcached.yaml
    repoURL: https://charts.bitnami.com/bitnami
    targetRevision: 7.8.6
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
