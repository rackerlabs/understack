{{- define "nautobot-understack.cnpgRwHost" -}}
{{- printf "%s-rw.%s.svc" .Values.understack.nautobot.cnpg.cluster.name .Release.Namespace -}}
{{- end -}}

{{- define "nautobot-understack.ssoSecretName" -}}
{{- $targetName := dig "spec" "target" "name" "" .Values.understack.nautobot.sso.externalSecret -}}
{{- if ne $targetName "" -}}
{{- $targetName -}}
{{- else -}}
{{- .Values.understack.nautobot.sso.externalSecret.name -}}
{{- end -}}
{{- end -}}

{{- define "nautobot-understack.ssoConfigMapName" -}}
{{- include "nautobot-understack.ssoSecretName" . -}}
{{- end -}}

{{- define "nautobot-understack.nautobotServiceUrl" -}}
{{- printf "http://%s-default.%s.svc.cluster.local" .Release.Name .Release.Namespace -}}
{{- end -}}
