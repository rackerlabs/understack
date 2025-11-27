{{- range .Values.routes }}
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  {{- if .name }}
  name: {{ .name }}
  {{- else }}
  {{- $name := index (splitList "." .fqdn) 0 }}
  name: {{ $name }}
  {{- end }}
  namespace: {{ .namespace | default "openstack" }}
spec:
  parentRefs:
    - name: {{ $.Values.gateways.external.name }}
      namespace: {{ $.Values.gateways.external.namespace }}
  hostnames: [{{ .fqdn | quote }}]
  rules:
    - matches:
        - path:
            type: {{ .pathType | default "PathPrefix" }}
            value: {{ .path | default "/" }}
      backendRefs:
        - name: {{ .service.name }}
          {{- with .namespace }}
          namespace: {{ . }}
          {{- end }}
          port: {{ .service.port }}
{{- end }}
