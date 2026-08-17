{{- if .Values.rbac.create }}
{{- $clusterWide := eq .Values.rbac.clusterWide true }}
{{- $rules := list }}
{{- $rules = append $rules (dict "apiGroups" (list "") "resources" (list "secrets") "verbs" (list "get")) }}
{{- range $rule := default list .Values.rbac.rules }}
{{- $rules = append $rules $rule }}
{{- end }}
{{- $configuredHooks := include "openstack-sync-operator.configuredHooks" . | fromYaml }}
{{- range $hookName, $hook := default dict $configuredHooks }}
{{- if eq $hook.enabled true }}
{{- $crdPath := get $hook "crd" }}
{{- if $crdPath }}
{{- $crd := include "openstack-sync-operator.hookCrd" (list $ $hookName $hook) | fromYaml }}
{{- $rules = append $rules (dict "apiGroups" (list $crd.group) "resources" (list $crd.plural) "verbs" (list "get" "list" "watch")) }}
{{- if $crd.hasStatus }}
{{- $rules = append $rules (dict "apiGroups" (list $crd.group) "resources" (list (printf "%s/status" $crd.plural)) "verbs" (list "get" "patch" "update")) }}
{{- end }}
{{- end }}
{{- end }}
{{- end }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: {{ ternary "ClusterRole" "Role" $clusterWide }}
metadata:
  name: {{ include "openstack-sync-operator.fullname" . }}
  labels:
    {{- include "openstack-sync-operator.labels" . | nindent 4 }}
    app.kubernetes.io/component: controller
{{- if gt (len $rules) 0 }}
rules:
{{- toYaml $rules | nindent 0 }}
{{- else }}
rules: []
{{- end }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: {{ ternary "ClusterRoleBinding" "RoleBinding" $clusterWide }}
metadata:
  name: {{ include "openstack-sync-operator.fullname" . }}
  labels:
    {{- include "openstack-sync-operator.labels" . | nindent 4 }}
    app.kubernetes.io/component: controller
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: {{ ternary "ClusterRole" "Role" $clusterWide }}
  name: {{ include "openstack-sync-operator.fullname" . }}
subjects:
- kind: ServiceAccount
  name: {{ include "openstack-sync-operator.serviceAccountName" . }}
  {{- if $clusterWide }}
  namespace: {{ .Release.Namespace }}
  {{- end }}
{{- end }}
