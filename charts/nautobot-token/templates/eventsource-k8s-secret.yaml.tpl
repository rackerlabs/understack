apiVersion: argoproj.io/v1alpha1
kind: EventSource
metadata:
  name: nautobot-token
  namespace: "{{ .Release.Namespace }}"
spec:
  eventBusName: nautobot-token
  template:
    serviceAccountName: k8s-list-secret-events
  resource:
    nautobot-token-upsert:
      namespace: "{{ .Release.Namespace }}"
      resource: secrets
      version: v1
      eventTypes:
        - ADD
        - UPDATE
      filter:
        labels:
          - key: token/type
            value: nautobot
