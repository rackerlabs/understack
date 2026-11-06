apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: {{ include "nautobotop.fullname" . }}-clusterrole
rules:
- apiGroups:
  - sync.rax.io
  resources:
  - nautobots
  - nautobots/status
  - nautobots/finalizers
  verbs:
  - get
  - list
  - watch
  - create
  - update
  - patch
  - delete
- apiGroups: [""]
  resources:
  - pods
  - services
  - configmaps
  - secrets
  - ingress
  - endpoints
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - apps
  resources:
  - deployments
  verbs:
  - get
  - list
  - watch
