---
apiVersion: generators.external-secrets.io/v1alpha1
kind: Password
metadata:
  name: "baremetal-vendor-{{ .Values.regionName }}"
spec:
  length: 32
  digits: 6
  symbols: 6
  symbolCharacters: "~!@#$%^*()_+-={}[]<>?"
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: "baremetal-vendor-{{ .Values.regionName }}"
spec:
  refreshInterval: 20160m
  target:
    name: baremetal-vendor
    template:
      engineVersion: v2
      type: Opaque
      metadata:
        annotations:
          understack.rackspace.com/keystone-roles: system-admin
        labels:
          keystone.understack.rackspace.com/account: "true"
          understack.rackspace.com/keystone-user: "baremetal-vendor-{{ .Values.regionName }}"
      data:
        password: "{{ `{{ .password }}` }}"
        clouds.yaml: |
          clouds:
            understack:
              auth:
                auth_url: "{{ .Values.keystoneUrl }}"
                user_domain_name: "service"
                username: "baremetal-vendor-{{ .Values.regionName }}"
                password: "{{ `{{ .password }}` }}"
                system_scope: "all"
              region_name: "{{ .Values.regionName }}"
              interface: "public"
              identity_api_version: 3
  dataFrom:
  - sourceRef:
      generatorRef:
        apiVersion: generators.external-secrets.io/v1alpha1
        kind: Password
        name: "baremetal-vendor-{{ .Values.regionName }}"
