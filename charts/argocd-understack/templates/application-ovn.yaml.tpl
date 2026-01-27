{{- if eq (include "understack.isEnabled" (list $.Values.site "ovn")) "true" }}
{{- $app := $.Values.site.ovn }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ printf "%s-%s" $.Release.Name "ovn" }}
spec:
  destination:
    namespace: {{ $.Values.site.openstack.namespace }}
    server: {{ $.Values.cluster_server }}
  project: understack
  sources:
  - repoURL: https://tarballs.opendev.org/openstack/openstack-helm-infra
    targetRevision: {{ $app.chartVersion }}
    chart: ovn
    helm:
      ignoreMissingValueFiles: true
      releaseName: ovn
      valueFiles:
      - $understack/components/images-openstack.yaml
      - $understack/components/ovn/values.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/manifests/secret-openstack.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/manifests/images-openstack.yaml
      - $deploy/{{ include "understack.deploy_path" $ }}/helm-configs/ovn.yaml
  - path: components/ovn/
    ref: understack
    repoURL: {{ include "understack.understack_url" $ }}
    targetRevision: {{ include "understack.understack_ref" $ }}
  - path: {{ include "understack.deploy_path" $ }}/manifests/ovn
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
