---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  labels:
    {{- include "dexop.labels" . | nindent 4 }}
  name: dexop-manager-rolebinding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: dexop-manager-role
subjects:
- kind: ServiceAccount
  name: {{ include "dexop.serviceAccountName" . }}
  namespace: {{ .Release.Namespace }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: dexop-metrics-auth-rolebinding
  labels:
    {{- include "dexop.labels" . | nindent 4 }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: dexop-metrics-auth-role
subjects:
- kind: ServiceAccount
  name: {{ include "dexop.serviceAccountName" . }}
  namespace: {{ .Release.Namespace }}
