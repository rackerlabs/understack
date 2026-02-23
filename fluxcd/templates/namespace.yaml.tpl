---
apiVersion: v1
kind: Namespace
metadata:
  name: flux-system
  labels:
    app.kubernetes.io/managed-by: Helm
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/enforce: restricted
---
apiVersion: v1
kind: Namespace
metadata:
  name: cilium
  labels:
    app.kubernetes.io/managed-by: FluxCD
    pod-security.kubernetes.io/audit: privileged
    pod-security.kubernetes.io/enforce: privileged
---
apiVersion: v1
kind: Namespace
metadata:
  name: cert-manager
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: cnpg-system
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: dex
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: envoy-gateway
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: external-dns
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: external-secrets
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: ingress-nginx
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: monitoring
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: nautobot
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: openstack
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: openstack-resource-controller
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: opentelemetry-operator
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: otel-collector
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: rook
  labels:
    app.kubernetes.io/managed-by: FluxCD
    pod-security.kubernetes.io/audit: privileged
    pod-security.kubernetes.io/enforce: privileged
---
apiVersion: v1
kind: Namespace
metadata:
  name: sealed-secrets
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: argo-events
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: argo-workflows
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: rabbitmq-system
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: undersync
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: snmp-exporter
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: chrony
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: mariadb-operator
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: etcdbackup
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: global-workflows
  labels:
    app.kubernetes.io/managed-by: FluxCD
---
apiVersion: v1
kind: Namespace
metadata:
  name: openebs
  labels:
    app.kubernetes.io/managed-by: FluxCD
