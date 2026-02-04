{{- if eq (include "understack.isEnabled" (list $.Values.global "nautobotop")) "true" }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "nautobotop" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: nautobotop
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - chart: nautobotop
    helm:
      ignoreMissingValueFiles: true
      releaseName: nautobotop
      valueFiles:
      - $deploy/{{ include "understack.deploy_path" $ }}/nautobotop/values.yaml
    repoURL: ghcr.io/rackerlabs/charts
    targetRevision: 0.0.1
  - path: {{ include "understack.deploy_path" $ }}/nautobotop
    ref: deploy
    repoURL: {{ include "understack.deploy_url" $ }}
    targetRevision: {{ include "understack.deploy_ref" $ }}
  - path: workflows/nautobot-token
    helm:
      ignoreMissingValueFiles: true
      valueFiles:
      - $understack/workflows/nautobot-token/values.yaml
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
