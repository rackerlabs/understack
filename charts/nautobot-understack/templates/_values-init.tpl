{{- /*
Derive upstream Nautobot dependency values from the UnderStack wrapper contract.
This keeps CNPG cluster naming as the source of truth for the database hostname.
*/ -}}
{{- if and .Values.understack.nautobot.cnpg.enabled (empty .Values.nautobot.nautobot.db.host) -}}
{{- $_ := set .Values.nautobot.nautobot.db "host" (include "nautobot-understack.cnpgRwHost" .) -}}
{{- end -}}
{{- if not (hasKey .Values.nautobot.nautobot "image") -}}
{{- $_ := set .Values.nautobot.nautobot "image" (dict) -}}
{{- end -}}
{{- if empty .Values.nautobot.nautobot.image.tag -}}
{{- $_ := set .Values.nautobot.nautobot.image "tag" .Chart.AppVersion -}}
{{- end -}}
{{- if and .Values.understack.nautobot.sso.configMap.enabled (eq (len .Values.nautobot.nautobot.extraEnvVarsCM) 0) -}}
{{- $_ := set .Values.nautobot.nautobot "extraEnvVarsCM" (list (include "nautobot-understack.ssoConfigMapName" .)) -}}
{{- end -}}
{{- if and (gt (len .Values.nautobot.nautobot.extraVolumes) 0) (empty (index .Values.nautobot.nautobot.extraVolumes 0).secret.secretName) -}}
{{- $_ := set (index .Values.nautobot.nautobot.extraVolumes 0).secret "secretName" (include "nautobot-understack.ssoSecretName" .) -}}
{{- end -}}
{{- if and .Values.understack.nautobot.postDeployJob.enabled (empty .Values.understack.nautobot.postDeployJob.nautobotUrl) -}}
{{- $_ := set .Values.understack.nautobot.postDeployJob "nautobotUrl" (include "nautobot-understack.nautobotServiceUrl" .) -}}
{{- end -}}
{{- if and .Values.understack.nautobot.postDeployJob.enabled (empty .Values.understack.nautobot.postDeployJob.image.tag) -}}
{{- $_ := set .Values.understack.nautobot.postDeployJob.image "tag" .Chart.AppVersion -}}
{{- end -}}
