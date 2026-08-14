{{- if .Values.serviceAccount.create }}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{include "openstack-sync-operator.serviceAccountName" .}}
  labels:
  {{- include "openstack-sync-operator.labels" . | nindent 4 }}
    app.kubernetes.io/component: controller
{{- end }}
