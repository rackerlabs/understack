{{- if .Values.gateways.external }}
{{- range .Values.routes.tls }}
{{- if .clientTrafficPolicy }}
{{- $listenerName := .name | default (index (splitList "." .fqdn) 0) }}
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: ClientTrafficPolicy
metadata:
  name: {{ .clientTrafficPolicy.name | default (printf "%s-client-traffic" $listenerName) }}
  namespace: {{ .clientTrafficPolicy.namespace | default $.Values.gateways.external.namespace }}
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: {{ $.Values.gateways.external.name }}
      sectionName: {{ $listenerName }}
  {{- with .clientTrafficPolicy.tcpKeepalive }}
  tcpKeepalive:
    {{- if .idleTime }}
    idleTime: {{ .idleTime }}
    {{- end }}
    {{- if .interval }}
    interval: {{ .interval }}
    {{- end }}
    {{- if .probes }}
    probes: {{ .probes }}
    {{- end }}
  {{- end }}
{{- end }}
{{- end }}
{{- end }}
