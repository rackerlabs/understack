---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: k8s-job-create
  namespace: "{{ .Release.Namespace }}"

---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: "{{ .Release.Namespace }}-job-creator"
  namespace: nautobot
rules:
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["create"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: "{{ .Release.Namespace }}-job-creator-binding"
  namespace: nautobot
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: "{{ .Release.Namespace }}-job-creator"
subjects:
  - kind: ServiceAccount
    name: k8s-job-create
    namespace: "{{ .Release.Namespace }}"
