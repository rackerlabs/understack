apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: diagnostics
  annotations:
    # Keep the stored files when the Argo CD app or this chart is removed.
    argocd.argoproj.io/sync-options: Delete=false,Prune=false
    helm.sh/resource-policy: keep
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: {{ .Values.storageClassName }}
  resources:
    requests:
      storage: {{ .Values.storageSize }}
