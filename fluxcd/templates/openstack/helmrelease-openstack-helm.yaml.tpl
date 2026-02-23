{{- if eq (include "fluxcd.isEnabled" (list $.Values.site "openstack")) "true" }}
{{- $root := . -}}
{{- $namespace := .Values.site.openstack.namespace -}}
{{- $repoUrl := .Values.site.openstack.repoUrl -}}
{{- range $appName := list "keystone" "glance" "cinder" "ironic" "neutron" "placement" "nova" "octavia" "horizon" "skyline" "openvswitch" "ovn" }}
{{- if eq (include "fluxcd.isEnabled" (list $.Values.site $appName)) "true" }}
{{- $app := get $.Values.site $appName }}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata:
  name: {{ printf "%s-%s" $root.Release.Name $appName }}
  namespace: {{ $namespace }}
spec:
  interval: 1h0s
  releaseName: {{ $appName }}
  chart:
    spec:
      chart: {{ $appName }}
      version: {{ $app.chartVersion }}
      sourceRef:
        kind: HelmRepository
        namespace: flux-system
        name: openstack-helm
  install:
    createNamespace: true
    remediation:
      retries: 3
  upgrade:
    createNamespace: true
    remediation:
      retries: 3
{{- if hasKey $app "wave" }}
  dependsOn:
    {{- if eq $appName "keystone" }}
    - name: {{ printf "%s-%s" $root.Release.Name "mariadb-operator" }}
    - name: {{ printf "%s-%s" $root.Release.Name "rabbitmq-system" }}
    {{- else if eq $appName "glance" }}
    - name: {{ printf "%s-%s" $root.Release.Name "keystone" }}
    {{- else if or (eq $appName "cinder") (eq $appName "ironic") (eq $appName "neutron") (eq $appName "placement") }}
    - name: {{ printf "%s-%s" $root.Release.Name "keystone" }}
    {{- else if eq $appName "nova" }}
    - name: {{ printf "%s-%s" $root.Release.Name "neutron" }}
    - name: {{ printf "%s-%s" $root.Release.Name "placement" }}
    {{- else if eq $appName "octavia" }}
    - name: {{ printf "%s-%s" $root.Release.Name "keystone" }}
    {{- else if eq $appName "horizon" }}
    - name: {{ printf "%s-%s" $root.Release.Name "keystone" }}
    {{- else if eq $appName "skyline" }}
    - name: {{ printf "%s-%s" $root.Release.Name "keystone" }}
    {{- else if eq $appName "openvswitch" }}
    - name: {{ printf "%s-%s" $root.Release.Name "keystone" }}
    {{- else if eq $appName "ovn" }}
    - name: {{ printf "%s-%s" $root.Release.Name "keystone" }}
    {{- end }}
{{- end }}
{{- end }}
{{- end }}
{{- end }}
