{{- /*
Validate cross-field relationships in the UnderStack Nautobot wrapper values.
This file intentionally emits no resources and only fails rendering on invalid
combinations.
*/ -}}
{{- $cnpg := .Values.understack.nautobot.cnpg -}}
{{- $db := .Values.nautobot.nautobot.db -}}
{{- $ssoConfig := .Values.understack.nautobot.sso.configMap -}}
{{- $ssoSecret := .Values.understack.nautobot.sso.externalSecret -}}

{{- if and (not $cnpg.enabled) (empty $db.host) -}}
{{- fail "nautobot.nautobot.db.host must be set when understack.nautobot.cnpg.enabled is false" -}}
{{- end -}}

{{- if and $cnpg.backup.enabled (ne $cnpg.backup.destinationPath "") (eq $cnpg.backup.secretName "") -}}
{{- fail "understack.nautobot.cnpg.backup.secretName must be set when understack.nautobot.cnpg.backup.destinationPath is configured" -}}
{{- end -}}

{{- if and $cnpg.backup.enabled (eq $cnpg.backup.destinationPath "") (ne $cnpg.backup.secretName "") -}}
{{- fail "understack.nautobot.cnpg.backup.destinationPath must be set when understack.nautobot.cnpg.backup.secretName is configured" -}}
{{- end -}}

{{- if and $ssoConfig.enabled (not $ssoSecret.enabled) -}}
{{- fail "understack.nautobot.sso.externalSecret.enabled must be true when understack.nautobot.sso.configMap.enabled is true" -}}
{{- end -}}

{{- if and $ssoSecret.enabled (empty $ssoSecret.name) -}}
{{- fail "understack.nautobot.sso.externalSecret.name must be set when understack.nautobot.sso.externalSecret.enabled is true" -}}
{{- end -}}

{{- if and $ssoSecret.enabled (not (hasKey $ssoSecret "spec")) -}}
{{- fail "understack.nautobot.sso.externalSecret.spec must be set when understack.nautobot.sso.externalSecret.enabled is true" -}}
{{- end -}}

{{- if and $ssoSecret.enabled (empty $ssoSecret.spec) -}}
{{- fail "understack.nautobot.sso.externalSecret.spec must not be empty when understack.nautobot.sso.externalSecret.enabled is true" -}}
{{- end -}}
