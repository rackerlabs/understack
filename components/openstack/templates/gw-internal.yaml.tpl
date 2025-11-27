{{- if .Values.gateways.internal }}
---
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: {{ .Values.gateways.internal.name }}
  namespace: {{ .Values.gateways.internal.namespace }}
spec:
  gatewayClassName: {{ .Values.gateways.internal.className }}
  listeners:
    - name: http
      protocol: HTTP
      port: {{ .Values.gateways.internal.port | default 80 }}
      allowedRoutes:
        namespaces:
          from: All
{{- end }}
