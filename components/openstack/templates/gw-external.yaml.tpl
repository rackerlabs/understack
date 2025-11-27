{{- if .Values.gateways.external }}
---
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: {{ .Values.gateways.external.name }}
  namespace: {{ .Values.gateways.external.namespace }}
  annotations:
    cert-manager.io/cluster-issuer: {{ .Values.gateways.external.issuer | default "understack-cluster-issuer"}}
spec:
  gatewayClassName: {{ .Values.gateways.external.className }}
  listeners:
    {{- range .Values.routes }}
    - name: {{ .name }}
      port: {{ $.Values.gateways.external.port | default 443 }}
      protocol: HTTPS
      hostname: {{ .fqdn | quote }}
      tls:
        mode: Terminate
        certificateRefs:
          - name: {{ .name }}-gtls

    {{- end }}
{{- end }}
