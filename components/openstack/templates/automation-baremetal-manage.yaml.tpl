---
apiVersion: generators.external-secrets.io/v1alpha1
kind: Password
metadata:
  name: "baremetal-manage-{{ .Values.regionName }}"
spec:
  length: 32
  digits: 6
  symbols: 4
  symbolCharacters: "~!@#$%^*()_+-={}[]<>?"
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: "baremetal-manage-{{ .Values.regionName }}"
spec:
  refreshInterval: 20160m
  target:
    name: baremetal-manage
    template:
      engineVersion: v2
      type: Opaque
      metadata:
        labels:
          understack.rackspace.com/keystone-role: infra-readwrite
          understack.rackspace.com/keystone-user: "baremetal-manage-{{ .Values.regionName }}"
      data:
        password: "{{ `{{ .password }}` }}"
        clouds.yaml: |
          clouds:
            understack:
              auth:
                auth_url: "{{ .Values.keystoneUrl }}"
                user_domain_name: "service"
                username: "baremetal-manage-{{ .Values.regionName }}"
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
        name: "baremetal-manage-{{ .Values.regionName }}"
