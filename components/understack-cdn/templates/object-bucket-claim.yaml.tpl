{{- if .Values.cdn.objectBucketIsLocal }}
apiVersion: objectbucket.io/v1alpha1
kind: ObjectBucketClaim
metadata:
  name: {{ .Values.cdn.bucketName }}
spec:
  bucketName: {{ .Values.cdn.bucketName }}
  storageClassName: ceph-bucket
  additionalConfig:
    maxObjects: "1000"
    maxSize: {{ .Values.cdn.bucketMaxSize }}
{{- end }}
