---
apiVersion: argoproj.io/v1alpha1
kind: EventBus
metadata:
  name: nautobot-token
  namespace: "{{ .Release.Namespace }}"
spec:
  nats:
    native:
      # Optional, defaults to 3. If it is < 3, set it to 3, that is the minimal requirement.
      replicas: {{ .Values.eventBus.replicas }}
      # Optional, authen strategy, "none" or "token", defaults to "none"
      auth: {{ .Values.eventBus.auth }}

---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: nautobot-token-pdb
  namespace: "{{ .Release.Namespace }}"
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      controller: eventbus-controller
      eventbus-name: nautobot-token
