{{- if .Values.serviceMonitor.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {{ include "ironic-hardware-exporter.fullname" . }}
  labels:
    {{- include "ironic-hardware-exporter.labels" . | nindent 4 }}
spec:
  endpoints:
    - port: http
      path: /metrics
      interval: {{ .Values.serviceMonitor.interval | default "60s" }}
      scrapeTimeout: {{ .Values.serviceMonitor.scrapeTimeout | default "30s" }}
  selector:
    matchLabels:
      {{- include "ironic-hardware-exporter.selectorLabels" . | nindent 6 }}
{{- end }}
