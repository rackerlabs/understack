{{- /*
Create service account. Values already include serviceAccount.create and name.
*/ -}}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ include "nautobotop.fullname" . | trunc 63 | trimSuffix "-" }}
  labels:
    app.kubernetes.io/name: {{ include "nautobotop.name" . }}
    app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .Values.serviceAccount.annotations }}
  annotations:
{{ toYaml .Values.serviceAccount.annotations | indent 4 }}
{{- end }}
{{- if not .Values.serviceAccount.create }}
# Note: serviceAccount.create is false — expecting an existing SA with this name.
{{- end }}
