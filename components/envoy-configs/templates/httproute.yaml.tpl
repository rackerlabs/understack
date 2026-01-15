{{- range .Values.routes.http }}
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
  labels:
    {{- include "envoy-configs.labels" $ | nindent 4 }}
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
      {{- with .filters }}
      filters:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      backendRefs:
        {{- if eq .service.backendType "tls" }}
        - name: {{ .service.name }}
          group: gateway.envoyproxy.io
          kind: Backend
          {{- with .namespace }}
          namespace: {{ . }}
          {{- end }}
        {{- else }}
        - name: {{ .service.name }}
          {{- with .namespace }}
          namespace: {{ . }}
          {{- end }}
          port: {{ .service.port }}
        {{- end }}
      {{- if .timeouts }}
      timeouts:
        {{- if hasKey .timeouts "backendRequest" }}
        backendRequest: {{ .timeouts.backendRequest | default "15s"}}
        {{- end }}
        {{- if hasKey .timeouts "request" }}
        request: {{ .timeouts.request | default "15s"}}
        {{- end }}
      {{- end }}
{{- if eq .service.backendType "tls" }}
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: Backend
metadata:
  name: {{ .service.name }}
  namespace: {{ .namespace | default "openstack" }}
spec:
  endpoints:
    - fqdn:
        # standard in-cluster DNS name
        hostname: {{ .service.name }}.{{ .namespace }}.svc.cluster.local
        port: {{ .service.port }}
  tls:
    insecureSkipVerify: true
{{- end }}
{{- end }}
