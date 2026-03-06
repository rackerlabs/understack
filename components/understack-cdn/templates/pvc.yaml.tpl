# Persistent volume for the Nginx cache.
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: nginx-cache
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: openebs-lvm
  resources:
    requests:
      storage: 5Gi
