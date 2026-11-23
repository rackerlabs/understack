{{- if .Values.supportassist.enabled }}
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: supportassist
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: {{ .Values.supportassist.storageClassName }}
  resources:
    requests:
      storage: {{ .Values.supportassist.storageSize }}
{{- end }}
