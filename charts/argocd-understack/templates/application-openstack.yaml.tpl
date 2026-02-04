{{- if eq (include "understack.isEnabled" (list $.Values.site "openstack")) "true" }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "openstack" }}
  annotations:
    argocd.argoproj.io/compare-options: ServerSideDiff=true,IncludeMutationWebhook=true
  {{/*
  {{- with $app.wave }}
    argocd.argoproj.io/sync-wave: {{ quote . }}
  {{- end }}
  */}}
spec:
  destination:
    namespace: {{ .Values.site.openstack.namespace }}
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - path: components/openstack
    ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
    helm:
      ignoreMissingValueFiles: true
      valueFiles:
      - $deploy/{{ include "understack.deploy_path" $ }}/openstack/values.yaml
  - path: {{ include "understack.deploy_path" $ }}/openstack
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
