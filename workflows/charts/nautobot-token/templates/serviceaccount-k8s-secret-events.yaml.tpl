---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: k8s-list-secret-events
  namespace: "{{ .Release.Namespace }}"
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: k8s-list-secret-reader
  namespace: "{{ .Release.Namespace }}"
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["list", "watch"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: k8s-list-secret-reader-binding
  namespace: "{{ .Release.Namespace }}"
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: k8s-list-secret-reader
subjects:
  - kind: ServiceAccount
    name: k8s-list-secret-events
    namespace: "{{ .Release.Namespace }}"
