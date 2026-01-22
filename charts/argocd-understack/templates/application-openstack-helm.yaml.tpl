{{- range $appName := list
  "keystone"
  "glance"
  "cinder"
  "ironic"
  "neutron"
  "placement"
  "nova"
  "octavia"
  "horizon"
  "skyline"
}}
{{- if eq (include "understack.isEnabled" (list $.Values.site $appName)) "true" }}
{{- $app := get $.Values.site $appName }}
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
    namespace: {{ $.Values.site.openstack.namespace }}
    server: {{ $.Values.cluster_server }}
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
      - $deploy/{{ include "understack.deploy_path" $ }}/manifests/secret-openstack.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/manifests/images-openstack.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/helm-configs/{{ $appName }}.yaml
  - path: components/{{ $appName }}/
    ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
  - path: {{ include "understack.deploy_path" $ }}/manifests/{{ $appName }}
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
