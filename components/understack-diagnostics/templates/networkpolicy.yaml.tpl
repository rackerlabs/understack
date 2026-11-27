apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: diagnostics
spec:
  podSelector:
    matchLabels:
      app: diagnostics
  policyTypes:
    - Ingress
  # The upload port has no credentials, so only the envoy gateway may reach it.
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: envoy-gateway
