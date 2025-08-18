---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: eso-openstack
---
apiVersion: v1
kind: Secret
metadata:
  annotations:
    kubernetes.io/service-account.name: eso-openstack
  name: eso-openstack.service-account-token
type: kubernetes.io/service-account-token
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: eso-openstack-role
rules:
- apiGroups: [""]
  resources:
  - secrets
  verbs:
  - get
  - list
  - watch
  resourceNames:
  - svc-acct-argoworkflow
  - svc-acct-netapp
  - cinder-netapp-config
- apiGroups:
  - authorization.k8s.io
  resources:
  - selfsubjectrulesreviews
  verbs:
  - create
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: eso-openstack-rolebinding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: eso-openstack-role
subjects:
- kind: ServiceAccount
  name: eso-openstack
---
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: openstack
spec:
  provider:
    kubernetes:
      remoteNamespace: openstack
      server:
        caProvider:
          type: ConfigMap
          name: kube-root-ca.crt
          key: ca.crt
          namespace: openstack
      auth:
        serviceAccount:
          name: eso-openstack
          namespace: openstack
