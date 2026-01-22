{{- if eq (include "understack.isEnabled" (list $.Values.global "dex")) "true" }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "dex" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: dex
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - chart: dex
    helm:
      ignoreMissingValueFiles: true
      releaseName: dex
      valueFiles:
      - $understack/components/dex/values.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/helm-configs/dex.yaml
    repoURL: https://charts.dexidp.io
    targetRevision: 0.16.0
  - path: components/dex
    ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
  - path: {{ include "understack.deploy_path" $ }}/manifests/dex
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
