{{- define "openstack.serviceuser.user_domain_name" -}}
{{- eq .usage "admin" | ternary "default" "service" }}
{{- end }}

{{- define "openstack.serviceuser.project_domain_name" -}}
{{-  eq .usage "admin" | ternary "default" ( default "service" .project_domain_name ) }}
{{- end }}

{{- define "openstack.serviceuser.project_name" -}}
{{- eq .usage "admin" | ternary "admin" ( default "service" .project_name ) }}
{{- end }}
