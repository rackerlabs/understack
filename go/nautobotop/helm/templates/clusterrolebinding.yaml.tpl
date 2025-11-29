apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {{ include "nautobotop.fullname" . }}-clusterrolebinding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: {{ include "nautobotop.fullname" . }}-clusterrole
subjects:
- kind: ServiceAccount
  name: {{ include "nautobotop.fullname" . | trunc 63 | trimSuffix "-" }}
  namespace: {{ .Release.Namespace }}