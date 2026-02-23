---
# Root Kustomization - commented out since Helm chart manages FluxCD resources directly
# apiVersion: kustomize.toolkit.fluxcd.io/v1
# kind: Kustomization
# metadata:
#   name: understack-fluxcd-root
#   namespace: flux-system
# spec:
#   interval: 1m0s
#   prune: {{ .Values.sync.prune }}
#   selfHeal: {{ .Values.sync.selfHeal }}
#   sourceRef:
#     kind: GitRepository
#     name: understack
#   path: ./fluxcd/templates
#   postBuild:
#     substitute:
#       cluster_server: {{ .Values.cluster_server }}
#       understack_url: {{ .Values.understack_url }}
#       understack_ref: {{ .Values.understack_ref }}
#       deploy_url: {{ .Values.deploy_url | default "" }}
#       deploy_ref: {{ .Values.deploy_ref | default "HEAD" }}
#       deploy_path_prefix: {{ .Values.deploy_path_prefix | default "" }}
#       release_name: {{ .Release.Name }}
