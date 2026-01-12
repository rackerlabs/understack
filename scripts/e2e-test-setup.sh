#!/bin/bash
set -euo pipefail

#SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Cluster names
MGMT_CLUSTER="mgmt"
GLOBAL_CLUSTER="global"
SITE_CLUSTER="site"

cleanup() {
    echo "Cleaning up clusters..."
    kind delete cluster --name "${SITE_CLUSTER}" || true
    kind delete cluster --name "${GLOBAL_CLUSTER}" || true
    kind delete cluster --name "${MGMT_CLUSTER}" || true
}

create_clusters() {
    echo "Creating management cluster..."
    kind create cluster --name "${MGMT_CLUSTER}"

    echo "Creating global cluster..."
    kind create cluster --name "${GLOBAL_CLUSTER}"

    echo "Creating site cluster..."
    kind create cluster --name "${SITE_CLUSTER}"
}

install_argocd() {
    echo "Installing ArgoCD..."
    kubectl --context "kind-${MGMT_CLUSTER}" create namespace argocd
    kubectl --context "kind-${MGMT_CLUSTER}" apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

    # Wait for ArgoCD to be ready
    kubectl --context "kind-${MGMT_CLUSTER}" wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd
}

setup_cluster_access() {
    echo "Setting up cluster access..."

    # Register global cluster
    register_cluster "${GLOBAL_CLUSTER}" "global"

    # Register site cluster
    register_cluster "${SITE_CLUSTER}" "site"

    # Verify clusters are registered
    verify_clusters
}

verify_clusters() {
    echo "Verifying cluster registration..."

    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        local registered_clusters
        registered_clusters=$(kubectl --context "kind-${MGMT_CLUSTER}" get secrets -n argocd -l argocd.argoproj.io/secret-type=cluster -o name | wc -l)

        if [ "$registered_clusters" -ge 2 ]; then
            echo "✓ All clusters registered successfully"
            kubectl --context "kind-${MGMT_CLUSTER}" get secrets -n argocd -l argocd.argoproj.io/secret-type=cluster -o custom-columns=NAME:.metadata.name,CLUSTER:.stringData.name
            return 0
        fi

        echo "Waiting for clusters to register... ($((attempt + 1))/$max_attempts)"
        sleep 2
        ((attempt++))
    done

    echo "✗ Cluster registration verification failed"
    return 1
}

register_cluster() {
    local cluster_name="$1"
    local cluster_role="$2"
    echo "Registering ${cluster_name} cluster with ArgoCD..."

    # Get cluster config
    TARGET_SERVER=$(kubectl --context "kind-${cluster_name}" config view --minify -o jsonpath='{.clusters[0].cluster.server}')
    TARGET_CA=$(kubectl --context "kind-${cluster_name}" config view --raw --minify --flatten -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')

    # Create service account in target cluster
    kubectl --context "kind-${cluster_name}" apply -f - <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: argocd-manager
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: argocd-manager
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
- kind: ServiceAccount
  name: argocd-manager
  namespace: kube-system
EOF

    # Get token
    TOKEN=$(kubectl --context "kind-${cluster_name}" create token argocd-manager -n kube-system)

    # Add cluster to ArgoCD
    kubectl --context "kind-${MGMT_CLUSTER}" apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: ${cluster_name}-secret
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: cluster
  annotations:
    understack.rackspace.com/env: test
    understack.rackspace.com/partition: test
    understack.racksapce.com/role: ${cluster_role}
type: Opaque
stringData:
  name: ${cluster_name}
  server: ${TARGET_SERVER}
  config: |
    {
      "bearerToken": "${TOKEN}",
      "tlsClientConfig": {
        "caData": "${TARGET_CA}"
      }
    }
EOF
}

main() {
    if [ $# -eq 0 ]; then
        echo "Usage: $0 [setup|cleanup]"
        echo ""
        echo "Commands:"
        echo "  setup   - Create clusters, install ArgoCD, and deploy UnderStack"
        echo "  cleanup - Delete all test clusters"
        exit 1
    fi

    case "${1}" in
        "cleanup")
            cleanup
            ;;
        "setup")
            create_clusters
            install_argocd
            setup_cluster_access
            echo "Setup of three clusters is complete!"
            echo "ArgoCD UI: kubectl --context kind-mgmt port-forward svc/argocd-server -n argocd 8080:443"
            ;;
        *)
            echo "Usage: $0 [setup|cleanup]"
            exit 1
            ;;
    esac
}

main "$@"
