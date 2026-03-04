{{/* Expand the name of the chart. */}}
{{- define "nautobot-api-tokens.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Create a default fully qualified app name. */}}
{{- define "nautobot-api-tokens.fullname" -}}
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

{{/* Chart label value. */}}
{{- define "nautobot-api-tokens.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Common labels. */}}
{{- define "nautobot-api-tokens.labels" -}}
helm.sh/chart: {{ include "nautobot-api-tokens.chart" . }}
{{ include "nautobot-api-tokens.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* Selector labels. */}}
{{- define "nautobot-api-tokens.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nautobot-api-tokens.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Script config map name. */}}
{{- define "nautobot-api-tokens.scriptConfigMapName" -}}
{{- if .Values.scriptConfigMapName }}
{{- .Values.scriptConfigMapName | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-script" (include "nautobot-api-tokens.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end }}

{{/* Desired token names config map name. */}}
{{- define "nautobot-api-tokens.desiredConfigMapName" -}}
{{- printf "%s-desired" (include "nautobot-api-tokens.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/* Per-token job name. */}}
{{- define "nautobot-api-tokens.jobName" -}}
{{- $root := index . 0 -}}
{{- $token := index . 1 -}}
{{- printf "%s-%s" (include "nautobot-api-tokens.fullname" $root) $token.name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/* Cleanup job name. */}}
{{- define "nautobot-api-tokens.cleanupJobName" -}}
{{- printf "%s-cleanup" (include "nautobot-api-tokens.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}
