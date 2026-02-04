{{- if or (eq (include "understack.isEnabled" (list $.Values.global "monitoring")) "true") (eq (include "understack.isEnabled" (list $.Values.site "monitoring")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "monitoring" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: monitoring
    server: {{ $.Values.cluster_server }}
  project: understack-operators
  sources:
  - chart: prometheus-operator-crds
    helm:
      releaseName: prometheus-operator-crds
    repoURL: https://prometheus-community.github.io/helm-charts
    targetRevision: 24.0.2
  - chart: kube-prometheus-stack
    helm:
      ignoreMissingValueFiles: true
      releaseName: kube-prometheus-stack
      valueFiles:
      - $understack/operators/monitoring/values.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/manifests/monitoring/values.yaml
    repoURL: https://prometheus-community.github.io/helm-charts
    targetRevision: 79.5.0
  - path: operators/monitoring
    ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
  - path: {{ include "understack.deploy_path" $ }}/manifests/monitoring
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
