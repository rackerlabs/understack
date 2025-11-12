---
apiVersion: generators.external-secrets.io/v1alpha1
kind: Password
metadata:
  name: "infrasetup-{{ .Values.regionName }}"
spec:
  length: 32
  digits: 6
  symbols: 6
  symbolCharacters: "~!@#$%^*()_+-={}[]<>?"
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: "infrasetup-{{ .Values.regionName }}"
spec:
  refreshInterval: 20160m
  target:
    name: infrasetup
    template:
      engineVersion: v2
      type: Opaque
      metadata:
        labels:
          understack.rackspace.com/keystone-role: infra-readwrite
          understack.rackspace.com/keystone-user: "infrasetup-{{ .Values.regionName }}"
      data:
        password: "{{ `{{ .password }}` }}"
        clouds.yaml: |
          clouds:
            understack:
              auth:
                auth_url: "{{ .Values.keystoneUrl }}"
                user_domain_name: "service"
                username: "infrasetup-{{ .Values.regionName }}"
                password: "{{ `{{ .password }}` }}"
                project_domain_name: "infra"
                project_name: "baremetal"
              region_name: "{{ .Values.regionName }}"
              interface: "public"
              identity_api_version: 3
  dataFrom:
  - sourceRef:
      generatorRef:
        apiVersion: generators.external-secrets.io/v1alpha1
        kind: Password
        name: "infrasetup-{{ .Values.regionName }}"
