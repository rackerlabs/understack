{{- range .Values.routes.tcp }}
{{- $listenerName := .name | default (index (splitList "." .fqdn) 0) }}
---
apiVersion: gateway.networking.k8s.io/v1alpha2
kind: TCPRoute
metadata:
  name: {{ $listenerName }}
  namespace: {{ .namespace | default "envoy-gateway" }}
  labels:
    {{- include "envoy-configs.labels" $ | nindent 4 }}
spec:
  parentRefs:
    - name: {{ $.Values.gateways.external.name }}
      namespace: {{ $.Values.gateways.external.namespace }}
      sectionName: {{ $listenerName }}
  rules:
    - backendRefs:
        - name: {{ .service.name }}
          {{- with .namespace }}
          namespace: {{ . }}
          {{- end }}
          port: {{ .service.port }}
{{- end }}
