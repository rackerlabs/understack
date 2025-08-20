apiVersion: generators.external-secrets.io/v1alpha1
kind: Fake
metadata:
  name: svc-acct-argoworkflow
spec:
  data:
    # this provider needs to go away for a generated account
    # but it currently must be in sync with the keystone bootstrap
    # script
    user_domain: infra
    username: argoworkflow
    password: demo
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: svc-acct-argoworkflow
spec:
  refreshInterval: 1h
  target:
    name: svc-acct-argoworkflow
  dataFrom:
  - sourceRef:
      generatorRef:
        apiVersion: generators.external-secrets.io/v1alpha1
        kind: Fake
        name: svc-acct-argoworkflow
