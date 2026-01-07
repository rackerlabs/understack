{{- if or (eq (include "understack.isEnabled" (list $.Values.global "opentelemetry_operator")) "true") (eq (include "understack.isEnabled" (list $.Values.site "opentelemetry_operator")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "opentelemetry-operator" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: opentelemetry-operator
    server: {{ $.Values.cluster_server }}
  project: understack-operators
  sources:
  - chart: opentelemetry-operator
    helm:
      ignoreMissingValueFiles: true
      releaseName: opentelemetry-operator
      valueFiles:
      - $understack/operators/opentelemetry-operator/values.yaml
      - $deploy/{{ $.Release.Name }}/helm-configs/opentelemetry-operator.yaml
    repoURL: https://open-telemetry.github.io/opentelemetry-helm-charts
    targetRevision: 0.95.1
  - path: operators/opentelemetry-operator
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
