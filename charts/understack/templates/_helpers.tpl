{{/*
Expand the name of the chart.
*/}}
{{- define "understack.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "understack.fullname" -}}
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
{{- define "understack.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "understack.labels" -}}
helm.sh/chart: {{ include "understack.chart" . }}
{{ include "understack.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "understack.selectorLabels" -}}
app.kubernetes.io/name: {{ include "understack.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "understack.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "understack.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create a valid ArgoCD Application name
*/}}
{{- define "understack.argocdAppName" -}}
{{- $root := index . 0 }}
{{- $appName := index . 1 }}
{{- printf "%s-%s" $root.Release.Name $appName }}
{{- end }}

{{/*
Get the UnderStack repository URL
*/}}
{{- define "understack.understack_url" -}}
{{- .Values.understack_url }}
{{- end }}

{{/*
Get the UnderStack repository git reference
*/}}
{{- define "understack.understack_ref" -}}
{{- .Values.understack_ref }}
{{- end }}

{{/*
Get the deployment repository URL
*/}}
{{- define "understack.deploy_url" -}}
{{- .Values.deploy_url }}
{{- end }}

{{/*
Get the deployment repository git reference
*/}}
{{- define "understack.deploy_ref" -}}
{{- .Values.deploy_ref }}
{{- end }}
