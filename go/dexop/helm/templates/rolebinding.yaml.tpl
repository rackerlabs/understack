---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  labels:
    {{- include "dexop.labels" . | nindent 4 }}
  name: dexop-leader-election-rolebinding
  namespace: {{ .Release.Namespace }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: dexop-leader-election-role
subjects:
- kind: ServiceAccount
  name: {{ include "dexop.serviceAccountName" . }}
  namespace: {{ .Release.Namespace }}
