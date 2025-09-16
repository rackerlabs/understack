{{- if .Values.keystoneServiceUsers.enabled }}
{{- range $serviceName, $users := .Values.keystoneServiceUsers.services }}
{{- range $_, $user := $users }}
{{/* special override for the admin user since its in the bootstrap domain of default */}}
{{- $user_domain_name := eq $user.usage "admin" | ternary "default" "service" }}
{{- $project_domain_name := eq $user.usage "admin" | ternary "default" ( default "service" $user.project_domain_name ) }}
{{- $project_name := eq $user.usage "admin" | ternary "admin" ( default "service" $user.project_name ) }}
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: {{ (printf "%s-keystone-%s" $serviceName $user.usage) | quote }}
{{- if $.Values.keystoneServiceUsers.externalLinkAnnotationTemplate }}
  annotations:
    link.argocd.argoproj.io/external-link: {{ tpl $.Values.keystoneServiceUsers.externalLinkAnnotationTemplate (dict "remoteRef" $user.remoteRef) | quote }}
{{- end }}
spec:
  refreshInterval: {{ $.Values.externalSecretsRefreshInterval | default "1h" }}
  secretStoreRef:
    kind: {{ $.Values.keystoneServiceUsers.secretStore.kind | quote }}
    name: {{ $.Values.keystoneServiceUsers.secretStore.name | quote }}
  target:
    name: {{ (printf "%s-keystone-%s" $serviceName $user.usage) | quote }}
    template:
      engineVersion: v2
      data:
        OS_AUTH_URL: {{ $.Values.keystoneUrl | quote }}
        OS_DEFAULT_DOMAIN: 'default'
        OS_INTERFACE: {{ $.Values.keystoneServiceUsers.keystoneInterface | quote }}
        OS_PROJECT_DOMAIN_NAME: {{ $project_domain_name | quote }}
        OS_PROJECT_NAME: {{ $project_name | quote }}
        OS_USER_DOMAIN_NAME: {{ $user_domain_name | quote }}
        OS_USERNAME: {{ `{{ .username }}` | quote }}
        OS_PASSWORD: {{ `{{ .password }}` | quote }}
        OS_REGION_NAME: {{ $.Values.regionName | quote }}
  dataFrom:
  - extract:
      key: {{ $user.remoteRef | quote }}
{{- end }}
{{- end }}
{{- range $serviceName, $users := .Values.keystoneServiceUsers.services }}
{{- if not (eq $serviceName "keystone") }}
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: {{ (printf "%s-ks-etc" $serviceName) | quote }}
spec:
  refreshInterval: {{ $.Values.externalSecretsRefreshInterval | default "1h" }}
  secretStoreRef:
    kind: {{ $.Values.keystoneServiceUsers.secretStore.kind | quote }}
    name: {{ $.Values.keystoneServiceUsers.secretStore.name | quote }}
  target:
    name: {{ (printf "%s-ks-etc" $serviceName) | quote }}
    template:
      engineVersion: v2
      data:
        {{ (printf "%s_auth.conf" $serviceName) | quote }}: |
        {{- range $_, $user := $users }}
        {{- $section := $user.section | default $user.usage }}
        {{- $section := eq $section "user" | ternary "keystone_authtoken" $section -}}
        {{- $shouldSkip := or (eq $user.usage "test") (eq $user.usage "admin") }}
        {{- if not $shouldSkip }}
          [{{ $section }}]
          username={{ printf "{{ (fromJson .%s).username }}" $user.usage }}
          password={{ printf "{{ (fromJson .%s).password }}" $user.usage }}
          region_name={{ $.Values.regionName | quote }}
        {{- end }}
        {{- end }}
  data:
  {{/* default section name is the usage field */}}
  {{/* usage test and admin are special in OpenStack Helm and not added to the config file */}}
  {{- range $_, $user := $users -}}
  {{- $shouldSkip := or (eq $user.usage "test") (eq $user.usage "admin") -}}
  {{- if not $shouldSkip }}
    - secretKey: {{ $user.usage }}
      remoteRef:
        key: {{ $user.remoteRef | quote }}
  {{- end }}
  {{- end }}
{{- end }}
{{- end }}
{{- end }}
