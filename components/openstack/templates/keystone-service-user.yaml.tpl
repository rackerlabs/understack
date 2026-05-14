{{- if .Values.keystoneServiceUsers.enabled }}
{{- range $serviceName, $users := .Values.keystoneServiceUsers.services }}
{{- range $_, $user := $users }}
---
apiVersion: v1
kind: Secret
metadata:
  name: {{ (printf "%s-keystone-%s" $serviceName $user.usage) | quote }}
data:
  OS_AUTH_TYPE: v3oidcaccesstokenfile
  OS_AUTH_URL: {{ $.Values.keystoneUrl | quote }}
  OS_DEFAULT_DOMAIN: "default"
  OS_INTERFACE: {{ $.Values.keystoneServiceUsers.keystoneInterface | quote }}
  OS_PROJECT_DOMAIN_NAME: {{ include "openstack.serviceuser.project_domain_name" $user | quote }}
  OS_PROJECT_NAME: {{ include "openstack.serviceuser.project_name" $user | quote }}
  OS_USER_DOMAIN_NAME: {{ include "openstack.serviceuser.user_domain_name" $user | quote }}
  OS_REGION_NAME: {{ $.Values.regionName | quote }}
  OS_IDENTITY_PROVIDER: {{ $.Values.keystoneServiceUsers.identityProvider }}
  OS_PROTOCOL: openid
  OS_ACCESS_TOKEN_FILE: {{ $.Values.keystoneServiceUsers.accessTokenFile }}
{{- end }}
{{- end }}
{{- range $serviceName, $users := .Values.keystoneServiceUsers.services }}
{{- if not (eq $serviceName "keystone") }}
---
apiVersion: v1
kind: Secret
metadata:
  name: {{ (printf "%s-ks-etc" $serviceName) | quote }}
data:
  {{ (printf "%s_auth.conf" $serviceName) | quote }}: |
  {{- range $_, $user := $users }}
  {{- $section := $user.section | default $user.usage }}
  {{- $section := eq $section "user" | ternary "keystone_authtoken" $section -}}
  {{- $shouldSkip := or (eq $user.usage "test") (eq $user.usage "admin") }}
  {{- if not $shouldSkip }}
    [{{ $section }}]
    auth_type=v3oidcaccesstokenfile
    auth_url={{ $.Values.keystoneUrl }}
    identity_provider={{ $.Values.identityProvider }}
    protocol=openid
    access_token_file=/var/run/secrets/kubernetes.io/serviceaccount/token
    region_name={{ $.Values.regionName }}
  {{- end }}
  {{- end }}
{{- end }}
{{- end }}
{{- end }}
