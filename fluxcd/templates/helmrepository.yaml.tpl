{{- if .Values.helmRepositories.dex.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: dex
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.dex.url }}
  type: oci
{{- end }}

{{- if .Values.helmRepositories.external_dns.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: external-dns
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.external_dns.url }}
{{- end }}

{{- if .Values.helmRepositories.external_secrets.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: external-secrets
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.external_secrets.url }}
{{- end }}

{{- if .Values.helmRepositories.ingress_nginx.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: ingress-nginx
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.ingress_nginx.url }}
{{- end }}

{{- if .Values.helmRepositories.jetstack.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: jetstack
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.jetstack.url }}
{{- end }}

{{- if .Values.helmRepositories.nautobot.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: nautobot
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.nautobot.url }}
{{- end }}

{{- if .Values.helmRepositories.openebs.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: openebs
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.openebs.url }}
{{- end }}

{{- if .Values.helmRepositories.openstack_helm.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: openstack-helm
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.openstack_helm.url }}
  type: oci
{{- end }}

{{- if .Values.helmRepositories.openstack_helm_infra.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: openstack-helm-infra
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.openstack_helm_infra.url }}
  type: oci
{{- end }}

{{- if .Values.helmRepositories.prometheus_community.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: prometheus-community
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.prometheus_community.url }}
{{- end }}

{{- if .Values.helmRepositories.prometheus_crds.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: prometheus-crds
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.prometheus_crds.url }}
{{- end }}

{{- if .Values.helmRepositories.rabbitmq.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: rabbitmq
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.rabbitmq.url }}
{{- end }}

{{- if .Values.helmRepositories.sealed_secrets.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: sealed-secrets
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.sealed_secrets.url }}
{{- end }}

{{- if .Values.helmRepositories.opentelemetry.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: opentelemetry
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.opentelemetry.url }}
{{- end }}

{{- if .Values.helmRepositories.bitnami.enabled }}
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: bitnami
  namespace: flux-system
spec:
  interval: 1h0s
  url: {{ .Values.helmRepositories.bitnami.url }}
{{- end }}

---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: cnpg-system
  namespace: flux-system
spec:
  interval: 1h0s
  url: https://cloudnative-pg.github.io/charts
  type: oci
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: mariadb-operator
  namespace: flux-system
spec:
  interval: 1h0s
  url: https://mariadb-operator.github.io/mariadb-operator
  type: oci
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: openstack-exporter
  namespace: flux-system
spec:
  interval: 1h0s
  url: https://enable-k.org/helm-charts
  type: oci
---
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata:
  name: envoy-gateway
  namespace: flux-system
spec:
  interval: 1h0s
  url: https://gateway.envoyproxy.io/helm
  type: oci
