---
apiVersion: rabbitmq.com/v1beta1
kind: RabbitmqCluster
metadata:
  name: rabbitmq
  annotations:
    # do not allow ArgoCD to delete our cluster
    argocd.argoproj.io/sync-options: Delete=false
spec:
  replicas: 3
  persistence: {{ .Values.rabbitmq.persistence | toJson }}
  image: {{ .Values.rabbitmq.image |  default "rabbitmq:3.13.7-management" }} # renovate:ignore
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: openstack-control-plane
                operator: In
                values:
                  - enabled
    podAntiAffinity:
        requiredDuringSchedulingIgnoredDuringExecution:
        - labelSelector:
            matchLabels:
              app.kubernetes.io/name: rabbitmq
          topologyKey: kubernetes.io/hostname
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: pdb-rabbitmq
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: rabbitmq
