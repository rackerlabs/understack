{{- range $appName, $app := .Values.site.openstack.apps }}
{{- if $app.enabled }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name $appName }}
  {{/*
  {{- with $app.wave }}
  annotations:
    argocd.argoproj.io/sync-wave: {{ quote . }}
  {{- end }}
  */}}
spec:
  destination:
    namespace: openstack
    server: https://kubernetes.default.svc
  project: understack
  sources:
  - repoURL: {{ $.Values.site.openstack.repoUrl }}
    targetRevision: {{ $app.chartVersion }}
    chart: {{ $appName }}
    helm:
      ignoreMissingValueFiles: true
      releaseName: {{ $appName }}
      valueFiles:
      - $understack/components/images-openstack.yaml
      - $understack/components/{{ $appName }}/values.yaml
      - $deploy/{{ $.Release.Name }}/manifests/secret-openstack.yaml
      - $deploy/{{ $.Release.Name }}/manifests/images-openstack.yaml
      - $deploy/{{ $.Release.Name }}/helm-configs/{{ $appName }}.yaml
  - path: components/{{ $appName }}/
    ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
  - path: {{ $.Release.Name }}/manifests/{{ $appName }}
    ref: deploy
    repoURL: {{ include "understack.deploy_url" $ }}
    targetRevision: {{ include "understack.deploy_ref" $ }}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - ServerSideApply=false
    - RespectIgnoreDifferences=true
    - ApplyOutOfSyncOnly=true
{{- end }}
{{- end }}
