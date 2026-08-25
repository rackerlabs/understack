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
  {{- if .Values.gateways.internal.serviceAnnotations }}
  infrastructure:
    parametersRef:
          group: gateway.envoyproxy.io
          kind: EnvoyProxy
          name: {{ .Values.gateways.internal.name }}-proxy
  {{- end }}
{{- if .Values.gateways.internal.serviceAnnotations }}
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: EnvoyProxy
metadata:
  name: {{ .Values.gateways.internal.name }}-proxy
  namespace: {{ .Values.gateways.internal.namespace }}
spec:
  provider:
    type: Kubernetes
    kubernetes:
      {{- with .Values.gateways.internal.envoyDeployment }}
      envoyDeployment:
        {{- if .replicas }}
        replicas: {{ .replicas }}
        {{- end }}
        {{- if .container }}
        container:
          {{- if .container.resources }}
          resources:
            {{- .container.resources | toYaml | nindent 12 }}
          {{- end }}
        {{- end }}
      {{- end }}
      envoyService:
        annotations:
          {{- .Values.gateways.internal.serviceAnnotations | toYaml | nindent 10 }}
        externalTrafficPolicy: {{ .Values.gateways.internal.externalTrafficPolicy | default "Cluster" }}
{{- end }}
{{- end }}
