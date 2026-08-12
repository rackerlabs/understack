{{/*
Expand the name of the chart.
*/}}
{{- define "openstack-sync-operator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "openstack-sync-operator.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "openstack-sync-operator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "openstack-sync-operator.labels" -}}
helm.sh/chart: {{ include "openstack-sync-operator.chart" . }}
{{ include "openstack-sync-operator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "openstack-sync-operator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "openstack-sync-operator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use.
*/}}
{{- define "openstack-sync-operator.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "openstack-sync-operator.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Checksum for hook settings that affect shell-operator startup configuration.
*/}}
{{- define "openstack-sync-operator.hookConfigChecksum" -}}
{{- include "openstack-sync-operator.configuredHooks" . | fromYaml | toJson | sha256sum -}}
{{- end }}

{{/*
Normalize built-in plugin hooks and direct hook definitions.
*/}}
{{- define "openstack-sync-operator.configuredHooks" -}}
{{- $hooks := dict -}}
{{- $enabledPlugins := default dict .Values.plugins -}}
{{- range $pluginName, $plugin := default dict .Values.pluginData -}}
{{- $hook := default dict $plugin.hook -}}
{{- if gt (len $hook) 0 -}}
{{- $hookValues := dict -}}
{{- range $key, $value := $hook -}}
{{- $_ := set $hookValues $key $value -}}
{{- end -}}
{{- $_ := set $hookValues "enabled" (eq (get $enabledPlugins $pluginName) true) -}}
{{- $_ := set $hooks $pluginName $hookValues -}}
{{- end -}}
{{- end -}}
{{- range $hookName, $hook := default dict .Values.hooks -}}
{{- $_ := set $hooks $hookName $hook -}}
{{- end -}}
{{- $hooks | toYaml -}}
{{- end }}
