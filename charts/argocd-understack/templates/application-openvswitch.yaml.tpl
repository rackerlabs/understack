{{- if eq (include "understack.isEnabled" (list $.Values.site "openvswitch")) "true" }}
{{- $app := $.Values.site.openvswitch }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "openvswitch" }}
spec:
  destination:
    namespace: {{ $.Values.site.openstack.namespace }}
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - repoURL: https://tarballs.opendev.org/openstack/openstack-helm
    targetRevision: {{ $app.chartVersion }}
    chart: openvswitch
    helm:
      ignoreMissingValueFiles: true
      releaseName: openvswitch
      valueFiles:
      - $understack/components/images-openstack.yaml
      - $understack/components/openvswitch/values.yaml
      - $deploy/{{ $.Release.Name }}/manifests/secret-openstack.yaml
      - $deploy/{{ $.Release.Name }}/manifests/images-openstack.yaml
      - $deploy/{{ $.Release.Name }}/helm-configs/openvswitch.yaml
  - path: components/openvswitch/
    ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
  - path: {{ $.Release.Name }}/manifests/openvswitch
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
