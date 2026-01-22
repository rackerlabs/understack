{{- if or (eq (include "understack.isEnabled" (list $.Values.global "external_dns")) "true") (eq (include "understack.isEnabled" (list $.Values.site "external_dns")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "external-dns" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: external-dns
    server: {{ $.Values.cluster_server }}
  project: understack-operators
  sources:
  - chart: external-dns-rackspace
    helm:
      ignoreMissingValueFiles: true
      releaseName: external-dns-rackspace
      valueFiles:
      - $deploy/{{ include "understack.deploy_path" $ }}/helm-configs/external-dns.yaml
    repoURL: ghcr.io/rackerlabs/charts
    targetRevision: 0.2.0
  - path: {{ include "understack.deploy_path" $ }}/manifests/external-dns
    ref: deploy
    repoURL: {{ include "understack.deploy_url" $ }}
    targetRevision: {{ include "understack.deploy_ref" $ }}
  syncPolicy:
    automated:
      enabled: true
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
