apiVersion: v1
kind: Service
metadata:
  name: {{ include "ironic-hardware-exporter.fullname" . }}
  labels:
    {{- include "ironic-hardware-exporter.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    {{- include "ironic-hardware-exporter.selectorLabels" . | nindent 4 }}
