{{- define "fluxcd.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end -}}

{{- define "fluxcd.fullname" -}}
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
{{- end -}}

{{- define "fluxcd.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end -}}

{{- define "fluxcd.labels" -}}
helm.sh/chart: {{ include "fluxcd.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "fluxcd.selectorLabels" -}}
app.kubernetes.io/name: {{ include "fluxcd.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "fluxcd.understack_url" -}}
{{- .Values.understack_url }}
{{- end -}}

{{- define "fluxcd.understack_ref" -}}
{{- .Values.understack_ref }}
{{- end -}}

{{- define "fluxcd.deploy_url" -}}
{{- required "deploy_url is required. Please set it in your values file" .Values.deploy_url }}
{{- end -}}

{{- define "fluxcd.deploy_ref" -}}
{{- .Values.deploy_ref }}
{{- end -}}

{{- define "fluxcd.deploy_path" -}}
{{- if .Values.deploy_path_prefix -}}
{{- printf "%s/%s" .Values.deploy_path_prefix .Release.Name -}}
{{- else -}}
{{- .Release.Name -}}
{{- end -}}
{{- end -}}

{{- define "fluxcd.isEnabled" -}}
{{- $scope := index . 0 -}}
{{- $component := index . 1 -}}
{{- $result := true -}}
{{- $scopeEnabled := get $scope "enabled" -}}
{{- $result = and $result $scopeEnabled -}}
{{- $component := default (dict "enabled" false) (get $scope $component) -}}
{{- $componentEnabled := get $component "enabled" -}}
{{- $result = and $result $componentEnabled -}}
{{- ternary "true" "false" $result -}}
{{- end -}}

{{- define "fluxcd.syncOptions" -}}
{{- $opts := list -}}
{{- if .Values.sync.createNamespace -}}
{{- $opts = append $opts "CreateNamespace=true" -}}
{{- end -}}
{{- if .Values.sync.serverSideApply -}}
{{- $opts = append $opts "ServerSideApply=true" -}}
{{- end -}}
{{- $opts = append $opts "RespectIgnoreDifferences=true" -}}
{{- $opts = append $opts "ApplyOutOfSyncOnly=true" -}}
{{- toJson $opts -}}
{{- end -}}

{{- define "fluxcd.releaseName" -}}
{{- $root := index . 0 -}}
{{- $component := index . 1 -}}
{{- printf "%s-%s" $root.Release.Name $component -}}
{{- end -}}

{{- define "fluxcd.namespace" -}}
{{- $component := . -}}
{{- $ns := dict
  "cilium" "cilium"
  "cert-manager" "cert-manager"
  "cnpg-system" "cnpg-system"
  "dex" "dex"
  "envoy-gateway" "envoy-gateway"
  "external-dns" "external-dns"
  "external-secrets" "external-secrets"
  "ingress-nginx" "ingress-nginx"
  "monitoring" "monitoring"
  "nautobot" "nautobot"
  "nautobotop" "nautobotop"
  "openstack" "openstack"
  "opentelemetry-operator" "opentelemetry-operator"
  "otel-collector" "otel-collector"
  "rook" "rook"
  "sealed-secrets" "sealed-secrets"
  "argo-events" "argo-events"
  "argo-workflows" "argo-workflows"
  "rabbitmq-system" "rabbitmq-system"
  "undersync" "undersync"
  "snmp-exporter" "snmp-exporter"
  "chrony" "chrony"
  "mariadb-operator" "mariadb-operator"
  "keystone" "openstack"
  "glance" "openstack"
  "cinder" "openstack"
  "ironic" "openstack"
  "neutron" "openstack"
  "placement" "openstack"
  "nova" "openstack"
  "octavia" "openstack"
  "horizon" "openstack"
  "skyline" "openstack"
  "openvswitch" "openstack"
  "ovn" "openstack"
  "openstack-exporter" "openstack"
  "openstack-memcached" "openstack"
  "openstack-resource-controller" "openstack-resource-controller"
  "kube-prometheus-stack" "monitoring"
  "prometheus-crd" "monitoring"
  "etcdbackup" "etcdbackup"
  "nautobot-site" "nautobot"
  "site-workflows" "site-workflows"
  "argo-events-workflows" "argo-events"
  "global-workflows" "global-workflows"
  "envoy-configs" "envoy-gateway"
  "understack-cluster-issuer" "cert-manager"
  "openebs" "openebs"
-}}
{{- get $ns $component | default $component -}}
{{- end -}}
