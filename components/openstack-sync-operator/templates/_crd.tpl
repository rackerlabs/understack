{{/*
Read hook CRD metadata used by RBAC and shell-operator environment wiring.
*/}}
{{- define "openstack-sync-operator.hookCrd" -}}
{{- $root := index . 0 -}}
{{- $hookName := index . 1 -}}
{{- $hook := index . 2 -}}
{{- $crdPath := get $hook "crd" -}}
{{- if not $crdPath -}}
{{- fail (printf "hooks.%s.crd is required for CRD metadata" $hookName) -}}
{{- end -}}
{{- $crdYaml := required (printf "hooks.%s.crd file %s is empty or missing" $hookName $crdPath) ($root.Files.Get $crdPath) -}}
{{- $crd := fromYaml $crdYaml -}}
{{- if ne $crd.kind "CustomResourceDefinition" -}}
{{- fail (printf "hooks.%s.crd must point to a CustomResourceDefinition" $hookName) -}}
{{- end -}}
{{- $group := required (printf "hooks.%s.crd spec.group is required" $hookName) $crd.spec.group -}}
{{- $kind := required (printf "hooks.%s.crd spec.names.kind is required" $hookName) $crd.spec.names.kind -}}
{{- $plural := required (printf "hooks.%s.crd spec.names.plural is required" $hookName) $crd.spec.names.plural -}}
{{- $storageVersion := "" -}}
{{- $hasStatus := false -}}
{{- range $version := required (printf "hooks.%s.crd spec.versions is required" $hookName) $crd.spec.versions }}
{{- if $version.storage -}}
{{- $storageVersion = $version.name -}}
{{- end -}}
{{- if hasKey (default dict $version.subresources) "status" -}}
{{- $hasStatus = true -}}
{{- end -}}
{{- end -}}
{{- if not $storageVersion -}}
{{- fail (printf "hooks.%s.crd must define a storage version" $hookName) -}}
{{- end -}}
{{- dict
  "apiVersion" (printf "%s/%s" $group $storageVersion)
  "group" $group
  "hasStatus" $hasStatus
  "kind" $kind
  "plural" $plural
  "resource" (printf "%s.%s" $plural $group)
  | toYaml -}}
{{- end }}
