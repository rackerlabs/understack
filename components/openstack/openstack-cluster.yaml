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
