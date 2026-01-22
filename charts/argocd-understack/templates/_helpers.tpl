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
{{- required "deploy_url is required. Please set it in your values file" .Values.deploy_url }}
{{- end }}

{{/*
Get the deployment repository git reference
*/}}
{{- define "understack.deploy_ref" -}}
{{- .Values.deploy_ref }}
{{- end }}

{{/*
Get the base path within the deploy repository.
Always includes Release.Name, with an optional prefix from deploy_path_prefix.

Examples:
  deploy_path_prefix: ""        -> "uc-iad3-prod"
  deploy_path_prefix: "sites"   -> "sites/uc-iad3-prod"
  deploy_path_prefix: "us/east" -> "us/east/uc-iad3-prod"

Usage in valueFiles:
  - $deploy/{{ include "understack.deploy_path" $ }}/helm-configs/dex.yaml

Usage in source path:
  path: {{ include "understack.deploy_path" $ }}/manifests/dex
*/}}
{{- define "understack.deploy_path" -}}
{{- if .Values.deploy_path_prefix -}}
{{- printf "%s/%s" .Values.deploy_path_prefix .Release.Name -}}
{{- else -}}
{{- .Release.Name -}}
{{- end -}}
{{- end }}

{{/*
Check if a component is enabled by walking the configuration hierarchy.
Supports both "global" and "site" scopes with appropriate kill switches.

Arguments:
  - scope (".Values.global" or ".Values.site")
  - component name (e.g., "openstack", "argo_events")
  - OpenStack Helm app name (optional, e.g., "keystone", "glance")

For apps within a component, automatically handles the "apps" sublevel if it exists.

Usage:
  Global component: {{ include "understack.isEnabled" (list .Values.global "argocd") }}
    Checks: global.enabled AND global.argocd.enabled

  Site component: {{ include "understack.isEnabled" (list .Values.site "openstack") }}
    Checks: site.enabled AND site.openstack.enabled

Returns: "true" if all levels are enabled, empty string otherwise
Defaults to false if any path segment is missing.
*/}}
{{- define "understack.isEnabled" -}}
{{- $scope := index . 0 -}}
{{- $component := index . 1 -}}
{{- $result := true -}}
{{/* Check scope.enabled as kill switch (global.enabled or site.enabled) */}}
{{- $scopeEnabled := get $scope "enabled" -}}
{{- $result = and $result $scopeEnabled -}}
{{/* Check component level: scope.component.enabled */}}
{{- $component := get $scope $component -}}
{{- $componentEnabled := get $component "enabled" -}}
{{- $result = and $result $componentEnabled -}}
{{- ternary "true" "false" $result -}}
{{- end }}
