{{- if .Values.gateways.external }}
---
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: {{ .Values.gateways.external.name }}
  namespace: {{ .Values.gateways.external.namespace }}
  annotations:
    cert-manager.io/cluster-issuer: {{ .Values.gateways.external.issuer | default "understack-cluster-issuer"}}
  labels:
    {{- include "envoy-configs.labels" . | nindent 4 }}
spec:
  gatewayClassName: {{ .Values.gateways.external.className }}
  listeners:
    {{- range .Values.routes.http }}
    {{- $listenerName := .name | default (index (splitList "." .fqdn) 0) }}
    - name: {{ $listenerName }}
      port: {{ $.Values.gateways.external.port | default 443 }}
      protocol: HTTPS
      hostname: {{ .fqdn }}
      tls:
        mode: Terminate
        certificateRefs:
          - name: {{ $listenerName }}-tls
      allowedRoutes:
        namespaces:
          {{- if .selector }}
          from: Selector
          selector:
            {{- .selector | toYaml | nindent 12 }}
          {{- else }}
          from: {{ .from | default "All" }}
          {{- end }}
    {{- end }}
    {{- range .Values.routes.tls }}
    {{- $listenerName := .name | default (index (splitList "." .fqdn) 0) }}
    - name: {{ $listenerName }}
      port: {{ $.Values.gateways.external.port | default 443 }}
      protocol: TLS
      hostname: {{ .fqdn | quote }}
      tls:
        mode: Passthrough
        certificateRefs:
          - name: {{ $listenerName }}-tls
      allowedRoutes:
        namespaces:
          {{- if .selector }}
          from: Selector
          selector:
            {{- .selector | toYaml | nindent 12 }}
          {{- else }}
          from: {{ .from | default "All" }}
          {{- end }}
    {{- end }}
  {{- if .Values.gateways.external.serviceAnnotations }}
  infrastructure:
    parametersRef:
          group: gateway.envoyproxy.io
          kind: EnvoyProxy
          name: {{ .Values.gateways.external.name }}-proxy
  {{- end }}
{{- if .Values.gateways.external.serviceAnnotations }}
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: EnvoyProxy
metadata:
  name: {{ .Values.gateways.external.name }}-proxy
  namespace: {{ .Values.gateways.external.namespace }}
spec:
  provider:
    type: Kubernetes
    kubernetes:
      envoyService:
        annotations:
          {{- .Values.gateways.external.serviceAnnotations | toYaml | nindent 10 }}
        externalTrafficPolicy: {{ .Values.gateways.external.externalTrafficPolicy | default "Cluster" }}
{{- end }}
{{- end }}
