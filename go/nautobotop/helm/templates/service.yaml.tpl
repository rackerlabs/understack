apiVersion: v1
kind: Service
metadata:
  name: {{ include "nautobotop.fullname" . }}
  labels:
    {{- include "nautobotop.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    {{- include "nautobotop.selectorLabels" . | nindent 4 }}
