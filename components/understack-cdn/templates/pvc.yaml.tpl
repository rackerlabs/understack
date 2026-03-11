# Persistent volume for the Nginx cache.
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: nginx-cache
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: {{ .Values.cdn.CacheStorageClassName }}
  resources:
    requests:
      storage: {{ .Values.cdn.cacheSize }}
