#!/bin/bash

wait_for_cert_manager() {
  local cmd="kubectl apply -f bootstrap/cert-manager/cmchecker.yaml --dry-run=server"
  max_tries=10
  current_retry=1

  echo -n "Waiting for cert-manager to become available."
  until $cmd &>/dev/null; do
    if (( current_retry == max_tries )); then
      echo "Timed out waiting for cert-manager to come up."
      exit 1
    else
      echo -n "."
    fi
    sleep 2
    (( current_retry++ ))
  done
  echo " done."
}

check_required_binaries() {
  local missing_binaries=()

  if ! command -v kubectl &>/dev/null; then
    missing_binaries+=("kubectl")
  fi

  if ! command -v helm &>/dev/null; then
    missing_binaries+=("helm")
  fi

  if [ ${#missing_binaries[@]} -ne 0 ]; then
    echo "Error: Required binaries not found: ${missing_binaries[*]}"
    exit 1
  fi
}

check_required_binaries

CM_CHART_VERSION=v1.19.2
helm upgrade --install \
  cert-manager oci://quay.io/jetstack/charts/cert-manager:${CM_CHART_VERSION} \
  --create-namespace \
  --namespace cert-manager \
  --set crds.enabled=true \
  --set config.enableGatewayApi=true \
  --set config.apiVersion="controller.config.cert-manager.io/v1alpha1" \
  --set config.kind="ControllerConfiguration" \
  cert-manager

wait_for_cert_manager
kubectl kustomize --enable-helm bootstrap | kubectl apply --server-side -f -
kubectl apply -f bootstrap/cert-manager/issuer-kube-system-self-signed.yaml
export DEPLOY_NAME=selfsigned
export DNS_ZONE=local
cat bootstrap/argocd/ingress.yaml | envsubst | kubectl apply -f -
