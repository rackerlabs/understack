---
{{- range .Values.site.secrets }}
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: {{ .name }}
  namespace: {{ .namespace }}
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: {{ .secretStore }}
  target:
    name: {{ .name }}
    creationPolicy: Owner
    template:
      engineVersion: v2
      data:
{{- range $k, $v := .templateData }}
        {{ $k }}: {{ $v | quote }}
{{- end }}
  data:
{{- range .data }}
    - secretKey: {{ .secretKey }}
      remoteRef:
        key: {{ .remoteRef.key }}
        property: {{ .remoteRef.property }}
        conversionStrategy: {{ .remoteRef.conversionStrategy | default "Default" }}
        decodingStrategy: {{ .remoteRef.decodingStrategy | default "None" }}
        metadataPolicy: {{ .remoteRef.metadataPolicy | default "None" }}
{{- end }}
---
{{- end }}
