---
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: understack
  namespace: flux-system
spec:
  interval: 1m0s
  url: {{ include "fluxcd.understack_url" . }}
  ref:
    {{- if eq (include "fluxcd.understack_ref" .) "HEAD" }}
    branch: main
    {{- else }}
    tag: {{ include "fluxcd.understack_ref" . }}
    {{- end }}
  {{- if and .Values.git_credentials .Values.git_credentials.username }}
  secretRef:
    name: fluxcd-understack-git-credentials
  {{- end }}
