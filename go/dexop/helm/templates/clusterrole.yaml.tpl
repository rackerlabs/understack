---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: dexop-metrics-reader
  labels:
    {{- include "dexop.labels" . | nindent 4 }}
rules:
- nonResourceURLs:
  - /metrics
  verbs:
  - get
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: dexop-metrics-auth-role
  labels:
    {{- include "dexop.labels" . | nindent 4 }}
rules:
- apiGroups:
  - authentication.k8s.io
  resources:
  - tokenreviews
  verbs:
  - create
- apiGroups:
  - authorization.k8s.io
  resources:
  - subjectaccessreviews
  verbs:
  - create
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  labels:
    {{- include "dexop.labels" . | nindent 4 }}
  name: dexop-client-editor-role
rules:
- apiGroups:
  - dex.rax.io
  resources:
  - clients
  verbs:
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch
- apiGroups:
  - dex.rax.io
  resources:
  - clients/status
  verbs:
  - get
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  labels:
    {{- include "dexop.labels" . | nindent 4 }}
  name: dexop-client-viewer-role
rules:
- apiGroups:
  - dex.rax.io
  resources:
  - clients
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - dex.rax.io
  resources:
  - clients/status
  verbs:
  - get
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: dexop-manager-role
  labels:
    {{- include "dexop.labels" . | nindent 4 }}
rules:
- apiGroups:
  - ""
  resources:
  - secrets
  verbs:
  - get
  - list
  - patch
  - update
  - watch
- apiGroups:
  - dex.rax.io
  resources:
  - clients
  verbs:
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch
- apiGroups:
  - dex.rax.io
  resources:
  - clients/finalizers
  verbs:
  - update
- apiGroups:
  - dex.rax.io
  resources:
  - clients/status
  verbs:
  - get
  - patch
  - update
