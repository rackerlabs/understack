---
apiVersion: generators.external-secrets.io/v1alpha1
kind: Password
metadata:
  name: "infrasetup-system-{{ .Values.regionName }}"
spec:
  length: 32
  digits: 6
  symbols: 6
  symbolCharacters: "~!@#$%^*()_+-={}[]<>?"
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: "infrasetup-system-{{ .Values.regionName }}"
spec:
  refreshInterval: 20160m
  target:
    name: infrasetup-system
    template:
      engineVersion: v2
      type: Opaque
      metadata:
        labels:
          understack.rackspace.com/keystone-role: system-readwrite
          understack.rackspace.com/keystone-user: "infrasetup-system-{{ .Values.regionName }}"
      data:
        password: "{{ `{{ .password }}` }}"
        clouds.yaml: |
          clouds:
            understack:
              auth:
                auth_url: "{{ .Values.keystoneUrl }}"
                user_domain_name: "service"
                username: "infrasetup-system-{{ .Values.regionName }}"
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
        name: "infrasetup-system-{{ .Values.regionName }}"
