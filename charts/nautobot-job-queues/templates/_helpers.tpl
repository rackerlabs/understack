{{/* Expand the name of the chart. */}}
{{- define "nautobot-job-queues.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Create a default fully qualified app name. */}}
{{- define "nautobot-job-queues.fullname" -}}
{{- if contains .Chart.Name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/* Chart label value. */}}
{{- define "nautobot-job-queues.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Common labels. */}}
{{- define "nautobot-job-queues.labels" -}}
helm.sh/chart: {{ include "nautobot-job-queues.chart" . }}
{{ include "nautobot-job-queues.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* Selector labels. */}}
{{- define "nautobot-job-queues.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nautobot-job-queues.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Script config map name. */}}
{{- define "nautobot-job-queues.scriptConfigMapName" -}}
{{- printf "%s-script" (include "nautobot-job-queues.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/* Desired JobQueue config map name. */}}
{{- define "nautobot-job-queues.desiredConfigMapName" -}}
{{- printf "%s-desired" (include "nautobot-job-queues.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/* Ensure job name. */}}
{{- define "nautobot-job-queues.jobName" -}}
{{- printf "%s-ensure" (include "nautobot-job-queues.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}
