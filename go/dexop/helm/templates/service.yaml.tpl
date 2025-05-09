apiVersion: v1
kind: Service
metadata:
  name: {{ include "dexop.fullname" . }}-manager-metrics
  labels:
    {{- include "dexop.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: 8443
      targetPort: 8443
      protocol: TCP
      name: https
  selector:
    {{- include "dexop.selectorLabels" . | nindent 4 }}
