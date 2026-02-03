{{- if or (eq (include "understack.isEnabled" (list $.Values.global "etcdbackup")) "true") (eq (include "understack.isEnabled" (list $.Values.site "etcdbackup")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "etcdbackup" }}
  finalizers:
  - resources-finalizer.argocd.argoproj.io
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: kube-system
    server: {{ $.Values.cluster_server }}
  project: understack-infra
  sources:
  - helm:
      ignoreMissingValueFiles: true
      valueFiles:
      - $understack/components/etcdbackup/values.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/etcdbackup/values.yaml
    path: components/etcdbackup
    ref: understack
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
