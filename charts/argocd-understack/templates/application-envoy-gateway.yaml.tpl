{{- if or (eq (include "understack.isEnabled" (list $.Values.global "envoy_gateway")) "true") (eq (include "understack.isEnabled" (list $.Values.site "envoy_gateway")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "envoy-gateway" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: envoy-gateway
    server: {{ $.Values.cluster_server }}
  project: understack-infra
  sources:
  - chart: gateway-helm
    helm:
      ignoreMissingValueFiles: true
      releaseName: gateway-helm
      valueFiles:
      - $understack/components/envoy-gateway/values.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/envoy-gateway/values.yaml
    repoURL: docker.io/envoyproxy
    targetRevision: v1.6.0
  - path: components/envoy-gateway
    ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
  - path: {{ include "understack.deploy_path" $ }}/envoy-gateway
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
