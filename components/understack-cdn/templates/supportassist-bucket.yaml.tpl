{{- if .Values.supportassist.enabled }}
apiVersion: objectbucket.io/v1alpha1
kind: ObjectBucketClaim
metadata:
  name: supportassist
spec:
  bucketName: supportassist
  storageClassName: ceph-bucket
  additionalConfig:
    maxSize: {{ .Values.supportassist.bucketMaxSize | upper | quote }}
{{- end }}
