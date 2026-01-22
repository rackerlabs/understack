{{- if or (eq (include "understack.isEnabled" (list $.Values.global "openebs")) "true") (eq (include "understack.isEnabled" (list $.Values.site "openebs")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "openebs" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: openebs
    server: {{ $.Values.cluster_server }}
  project: understack-operators
  sources:
  - chart: openebs
    helm:
      ignoreMissingValueFiles: true
      releaseName: openebs
      valueFiles:
      - $understack/operators/openebs/values.yaml
      - $deploy/{{ $.Release.Name }}/helm-configs/openebs.yaml
    repoURL: https://openebs.github.io/openebs
    targetRevision: 4.4.0
  - path: operators/openebs
    ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
  - ref: deploy
    repoURL: {{ include "understack.deploy_url" $ }}
    targetRevision: {{ include "understack.deploy_ref" $ }}
    path: {{ include "understack.deploy_path" $ }}/manifests/openebs
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
