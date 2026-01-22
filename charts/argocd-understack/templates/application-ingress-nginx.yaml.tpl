{{- if or (eq (include "understack.isEnabled" (list $.Values.global "ingress_nginx")) "true") (eq (include "understack.isEnabled" (list $.Values.site "ingress_nginx")) "true") }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "ingress-nginx" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: ingress-nginx
    server: {{ $.Values.cluster_server }}
  project: understack-infra
  sources:
  - chart: ingress-nginx
    helm:
      ignoreMissingValueFiles: true
      releaseName: ingress-nginx
      valueFiles:
      - $deploy/{{ include "understack.deploy_path" $ }}/helm-configs/ingress-nginx.yaml
    repoURL: https://kubernetes.github.io/ingress-nginx
    targetRevision: 4.12.1
  - ref: deploy
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
