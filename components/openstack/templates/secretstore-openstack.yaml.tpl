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
  name: eso-openstack
rules:
- apiGroups: [""]
  resources:
  - secrets
  verbs:
  - get
  - list
  - watch
  resourceNames:
  - baremetal-manage
  - svc-acct-argoworkflow
  - svc-acct-netapp
  - cinder-netapp-config
  - admin-keystone-password
  - cinder-keystone-password
  - glance-keystone-password
  - ironic-keystone-password
  - neutron-keystone-password
  - nova-keystone-password
  - octavia-keystone-password
  - placement-keystone-password
  - skyline-keystone-password
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
  name: eso-openstack
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: eso-openstack
subjects:
- kind: ServiceAccount
  name: eso-openstack
---
apiVersion: external-secrets.io/v1
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
