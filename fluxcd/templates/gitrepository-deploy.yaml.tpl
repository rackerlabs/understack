{{- if .Values.deploy_url }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: deploy
  namespace: flux-system
spec:
  interval: 1m0s
  url: {{ include "fluxcd.deploy_url" . }}
  ref:
    {{- if eq (include "fluxcd.deploy_ref" .) "HEAD" }}
    branch: main
    {{- else }}
    tag: {{ include "fluxcd.deploy_ref" . }}
    {{- end }}
  {{- if and .Values.git_credentials .Values.git_credentials.username }}
  secretRef:
    name: fluxcd-deploy-git-credentials
  {{- end }}
{{- end }}
