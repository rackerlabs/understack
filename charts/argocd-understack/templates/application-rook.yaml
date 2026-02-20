{{- if or (eq (include "understack.isEnabled" (list $.Values.global "rook")) "true") (eq (include "understack.isEnabled" (list $.Values.site "rook")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "rook" }}
  finalizers:
  - resources-finalizer.argocd.argoproj.io
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: rook-ceph
    server: {{ $.Values.cluster_server }}
  project: understack-operators
  sources:
  - chart: rook-ceph
    helm:
      ignoreMissingValueFiles: true
      releaseName: rook-ceph
      valueFiles:
      - $understack/operators/rook/values-operator.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/rook-operator/values.yaml
    repoURL: https://charts.rook.io/release
    targetRevision: v1.16.4
  - chart: rook-ceph-cluster
    helm:
      ignoreMissingValueFiles: true
      releaseName: rook-ceph-cluster
      valueFiles:
      - $understack/operators/rook/values-cluster.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/rook-cluster/values.yaml
    repoURL: https://charts.rook.io/release
    targetRevision: v1.16.4
  - path: operators/rook
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
