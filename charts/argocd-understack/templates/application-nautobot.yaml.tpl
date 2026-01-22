{{- if eq (include "understack.isEnabled" (list $.Values.global "nautobot")) "true" }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "nautobot" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
spec:
  destination:
    namespace: nautobot
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - chart: nautobot
    helm:
      fileParameters:
      - name: nautobot.config
        path: $understack/components/nautobot/nautobot_config.py
      ignoreMissingValueFiles: true
      releaseName: nautobot
      valueFiles:
      - $understack/components/nautobot/values.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/helm-configs/nautobot.yaml
    repoURL: https://nautobot.github.io/helm-charts/
    targetRevision: 2.5.6
  - path: components/nautobot
    ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
  - path: {{ include "understack.deploy_path" $ }}/manifests/nautobot
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
